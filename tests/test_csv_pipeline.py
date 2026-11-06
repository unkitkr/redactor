"""Exercise actual analysis, identity resolution and durable CSV rewriting."""

import csv
import sqlite3
from pathlib import Path

from redactor.coordinator.bootstrap import prepare_run
from redactor.inference.ner import load_local_ner
from redactor.persistence.files.results import read_step_result
from redactor.persistence.queue.tasks import claim_task, iter_tasks, recover_interrupted
from redactor.schemas.analysis import FileAnalysis
from redactor.schemas.configuration import PipelineSettings, ResourceSettings
from redactor.workers.analyze import analyze_task
from redactor.workers.inspect import inspect_task
from redactor.workers.pipeline import execute_task
from redactor.workers.resolve import resolve_task
from redactor.workers.rewrite import rewrite_task


def test_csv_analysis_resolution_and_checkpoint_replay(
    connection: sqlite3.Connection, tmp_path: Path
) -> None:
    source = tmp_path / "input"
    source.mkdir()
    path = source / "records.csv"
    path.write_text(
        "patient,mrn,birth_date,admit_ts,dx_codes,comments\n"
        '"Smith, Jane",001-234,1965-10-16,2026-05-24,E11.9,'
        '"A1c 8.4%; metformin 1000 mg BID. Call daughter Lea at 415-555-0104."\n'
        '"Smith, Jane",001234,1965-10-16,2026-05-27,I10,'
        '"Follow up on 06/12/2026.\nLDL 92 mg/dL."\n'
    )
    settings = PipelineSettings(resources=ResourceSettings(checkpoint_records=1))
    key = bytes(range(32))
    ner = load_local_ner(settings.local)
    run = prepare_run(connection, source, settings, key)
    inspection = claim_task(connection, step="inspect")
    assert inspection is not None
    execute_task(
        connection,
        inspection,
        {
            "inspect": lambda db, task: inspect_task(
                db, task, resources=settings.resources, mapping_key=key
            )
        },
    )
    analysis = claim_task(connection, step="analyze")
    assert analysis is not None
    execute_task(
        connection,
        analysis,
        {
            "analyze": lambda db, task: analyze_task(
                db, task, resources=settings.resources, mapping_key=key, local_ner=ner
            )
        },
    )
    summary = read_step_result(
        connection, analysis.task_id, FileAnalysis, encryption_key=key
    )
    assert summary.reason is None
    assert summary.record_count == 2
    resolution = claim_task(connection, step="resolve")
    assert resolution is not None
    execute_task(
        connection,
        resolution,
        {"resolve": lambda db, task: resolve_task(db, task, mapping_key=key)},
    )
    rewrite = claim_task(connection, step="rewrite")
    assert rewrite is not None
    result = rewrite_task(
        connection,
        rewrite,
        settings=settings,
        mapping_key=key,
        local_ner=ner,
        resolution_task_id=run.resolution_task_id,
    )
    assert result.artifact is not None
    first_bytes = result.artifact.path.read_bytes()
    # A process can die after the final checkpoint but before accepting its result.
    recover_interrupted(connection)
    retry = claim_task(connection, step="rewrite")
    assert retry is not None
    replay = rewrite_task(
        connection,
        retry,
        settings=settings,
        mapping_key=key,
        local_ner=ner,
        resolution_task_id=run.resolution_task_id,
    )
    assert replay.artifact is not None
    assert replay.artifact.path.read_bytes() == first_bytes
    with replay.artifact.path.open(newline="") as stream:
        rows = list(csv.DictReader(stream))
    assert len(rows) == 2
    assert rows[0]["patient"] == rows[1]["patient"] != "Smith, Jane"
    assert rows[0]["mrn"] == rows[1]["mrn"] != "001234"
    assert rows[0]["dx_codes"] == "E11.9"
    assert "A1c 8.4%; metformin 1000 mg BID." in rows[0]["comments"]
    assert "LDL 92 mg/dL." in rows[1]["comments"]
    assert b"415-555-0104" not in first_bytes
    assert b"1965-10-16" not in first_bytes
    assert len(list(iter_tasks(connection))) == 4
