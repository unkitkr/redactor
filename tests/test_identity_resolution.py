"""Freeze real encrypted evidence across files, interruption and rejected sources."""

import csv
import signal
import sqlite3
import subprocess
import sys
from contextlib import closing
from datetime import date
from pathlib import Path

import pytest

from redactor.coordinator.bootstrap import prepare_run
from redactor.identity.evidence import prepare_observation
from redactor.identity.resolution import resolve_sources
from redactor.persistence.database import open_database, state_directory
from redactor.persistence.files.registration import register_file
from redactor.persistence.files.results import write_step_result
from redactor.persistence.identities.observations import save_observation_batch
from redactor.persistence.identities.resolution import resolution_progress
from redactor.persistence.identities.snapshots import load_identity_lookup
from redactor.persistence.identities.sources import resolution_sources
from redactor.persistence.queue.tasks import (
    claim_task,
    complete_task,
    get_task,
    recover_interrupted,
)
from redactor.schemas.analysis import FileAnalysis
from redactor.schemas.configuration import PipelineSettings
from redactor.schemas.identity import IdentityEvidence, ResolvedIdentity
from redactor.schemas.inventory import PreparedRun
from redactor.utils.constants import STEP_ANALYZE, STEP_INSPECT, STEP_RESOLVE
from redactor.utils.errors import (
    ERROR_IDENTITY_SNAPSHOT,
    ERROR_STALE_ATTEMPT,
    ERROR_STEP_RESULT,
    ERROR_STRUCTURE,
)
from redactor.workers.inspect import inspect_task
from redactor.workers.resolve import resolve_task


def test_identity_snapshot_matches_clean_run_after_sigkill_and_atomic_rollback(
    connection: sqlite3.Connection, tmp_path: Path
) -> None:
    key = bytes(range(32))
    anchor = IdentityEvidence(
        role="patient",
        name="John Smith",
        identifier="00123",
        identifier_namespace="mrn",
        birth_date=date(1936, 1, 2),
        reference_date=date(2025, 1, 2),
        context_key="anchor",
    )
    alias = anchor.model_copy(
        update={
            "name": "Smith, John",
            "birth_date": None,
            "reference_date": date(2026, 1, 2),
            "context_key": "alias",
        }
    )
    ambiguous = alias.model_copy(
        update={"name": "J. Smith", "context_key": "ambiguous"}
    )
    other = anchor.model_copy(
        update={
            "name": "Jane Smith",
            "birth_date": date(1980, 1, 2),
            "context_key": "other",
        }
    )
    provider = anchor.model_copy(
        update={
            "role": "provider",
            "birth_date": None,
            "context_key": "provider",
        }
    )
    rejected = anchor.model_copy(update={"reference_date": date(2099, 1, 2)})
    records = {
        "first.csv": (anchor,),
        "second.csv": (alias, ambiguous),
        "third.csv": (other, provider),
        "rejected.csv": (rejected,),
    }
    input_directory = tmp_path / "input"
    input_directory.mkdir()
    for filename, evidence in records.items():
        with (input_directory / filename).open("w", newline="") as stream:
            writer = csv.writer(stream)
            writer.writerow(("patient", "mrn", "birth_date", "event_date"))
            for item in evidence:
                writer.writerow(
                    (item.name, item.identifier, item.birth_date, item.reference_date)
                )
    run, analysis_ids = _seed_analysis(connection, input_directory, records)

    # Completed evidence from another run must not make this run's alias ambiguous.
    register_file(
        connection, input_directory / "first.csv", STEP_ANALYZE, "unrelated-run"
    )
    unrelated = claim_task(
        connection, step=STEP_ANALYZE, processing_version="unrelated-run"
    )
    assert unrelated is not None
    save_observation_batch(
        connection,
        unrelated,
        (anchor.model_copy(update={"birth_date": date(1975, 1, 2)}),),
        key,
        sequence=1,
        input_offset=unrelated.input_size,
        record_count=1,
    )
    complete_task(connection, unrelated)

    process = subprocess.run(
        [
            sys.executable,
            str(Path(__file__).parent / "support" / "crash_during_resolution.py"),
            str(state_directory(connection)),
        ],
        check=False,
        timeout=10,
    )
    assert process.returncode == -signal.SIGKILL
    stale = get_task(connection, run.resolution_task_id)
    before = resolution_progress(connection, stale.task_id)
    assert before.observation_count == 1
    with pytest.raises(ValueError, match=ERROR_STEP_RESULT):
        load_identity_lookup(connection, stale.task_id, key)
    recover_interrupted(connection)
    resumed = claim_task(connection, step=STEP_RESOLVE)
    assert resumed is not None
    sources = resolution_sources(connection, resumed.task_id)
    with pytest.raises(ValueError, match=ERROR_STALE_ATTEMPT):
        resolve_sources(connection, stale, sources, key)

    saved_cohorts = connection.execute(
        "SELECT * FROM identity_cohorts ORDER BY identity_key"
    ).fetchall()
    connection.execute(
        "CREATE TEMP TRIGGER reject_resolution "
        "BEFORE UPDATE ON identity_resolution_progress "
        "BEGIN SELECT RAISE(ABORT, 'test resolution failure'); END"
    )
    with pytest.raises(sqlite3.IntegrityError):
        resolve_sources(connection, resumed, sources, key)
    assert resolution_progress(connection, resumed.task_id) == before
    assert (
        connection.execute("SELECT count(*) FROM identity_bindings").fetchone()[0] == 1
    )
    assert (
        connection.execute(
            "SELECT * FROM identity_cohorts ORDER BY identity_key"
        ).fetchall()
        == saved_cohorts
    )
    connection.execute("DROP TRIGGER reject_resolution")
    result = resolve_task(connection, resumed, mapping_key=key)
    complete_task(connection, resumed, result=result.artifact)
    snapshot, lookup = load_identity_lookup(connection, resumed.task_id, key)
    assert (
        snapshot.source_count,
        snapshot.observation_count,
        snapshot.identity_count,
    ) == (3, 5, 4)

    def resolved(filename: str, evidence: IdentityEvidence) -> ResolvedIdentity:
        return lookup(
            analysis_ids[filename], prepare_observation(evidence, key).observation_key
        )

    patient = resolved("first.csv", anchor)
    linked = resolved("second.csv", alias)
    assert patient == linked
    assert patient.older_age_group is True
    assert patient.reference_date == date(2026, 1, 2)
    assert resolved("second.csv", ambiguous).match.status == "ambiguous"
    assert resolved("third.csv", other).match.identity_key != patient.match.identity_key
    assert resolved("third.csv", other).older_age_group is False
    assert (
        resolved("third.csv", provider).match.identity_key != patient.match.identity_key
    )
    with pytest.raises(ValueError, match=ERROR_IDENTITY_SNAPSHOT):
        resolved("rejected.csv", rejected)
    assert "John Smith" not in "\n".join(connection.iterdump())

    with closing(open_database(tmp_path / "clean-state")) as clean:
        clean_run, _ = _seed_analysis(clean, input_directory, records)
        clean_task = claim_task(clean, step=STEP_RESOLVE)
        assert clean_task is not None
        clean_result = resolve_task(clean, clean_task, mapping_key=key)
        complete_task(clean, clean_task, result=clean_result.artifact)
        clean_snapshot, _ = load_identity_lookup(
            clean, clean_run.resolution_task_id, key
        )
        assert clean_snapshot == snapshot

    # A changed binding cannot silently point at a different person's valid cohort.
    connection.execute(
        "UPDATE identity_bindings SET identity_key = ? WHERE resolution_task_id = ? "
        "AND source_task_id = ?",
        (
            resolved("third.csv", other).match.identity_key,
            resumed.task_id,
            analysis_ids["first.csv"],
        ),
    )
    _, fresh_lookup = load_identity_lookup(connection, resumed.task_id, key)
    with pytest.raises(ValueError, match=ERROR_IDENTITY_SNAPSHOT):
        fresh_lookup(
            analysis_ids["first.csv"], prepare_observation(anchor, key).observation_key
        )


def test_identity_aliases_resolve_identically_in_reversed_record_order(
    tmp_path: Path,
) -> None:
    key = bytes(range(32))
    evidence = tuple(
        IdentityEvidence(
            role="patient",
            name=name,
            identifier="27193",
            identifier_namespace="mrn",
            birth_date=date(1974, 2, 8),
            reference_date=date(2026, 1, 2),
            context_key=f"record-{index}",
        )
        for index, name in enumerate(
            ("Alex Stone", "Alex M Stone", "Alex Morgan Stone")
        )
    )
    expected: ResolvedIdentity | None = None
    for index, ordered in enumerate((evidence, tuple(reversed(evidence)))):
        source = tmp_path / str(index) / "input"
        source.mkdir(parents=True)
        with (source / "records.csv").open("w", newline="") as stream:
            writer = csv.writer(stream)
            writer.writerow(("patient", "mrn", "birth_date"))
            for person in ordered:
                writer.writerow((person.name, person.identifier, person.birth_date))
        with closing(open_database(tmp_path / str(index) / ".redactor")) as connection:
            run, sources = _seed_analysis(connection, source, {"records.csv": ordered})
            resolution = claim_task(connection, step=STEP_RESOLVE)
            assert resolution is not None
            result = resolve_task(connection, resolution, mapping_key=key)
            complete_task(connection, resolution, result=result.artifact)
            _, lookup = load_identity_lookup(connection, run.resolution_task_id, key)
            for person in ordered:
                resolved = lookup(
                    sources["records.csv"],
                    prepare_observation(person, key).observation_key,
                )
                assert resolved.match.status == "corroborated"
                if expected is None:
                    expected = resolved
                assert resolved == expected


def _seed_analysis(
    connection: sqlite3.Connection,
    input_directory: Path,
    records: dict[str, tuple[IdentityEvidence, ...]],
) -> tuple[PreparedRun, dict[str, str]]:
    key = bytes(range(32))
    settings = PipelineSettings()
    run = prepare_run(connection, input_directory, settings, key)
    while inspection := claim_task(connection, step=STEP_INSPECT):
        result = inspect_task(
            connection, inspection, resources=settings.resources, mapping_key=key
        )
        complete_task(connection, inspection, result=result.artifact)
    analysis_ids: dict[str, str] = {}
    while analysis := claim_task(connection, step=STEP_ANALYZE):
        evidence = records[analysis.input_path.name]
        save_observation_batch(
            connection,
            analysis,
            evidence,
            key,
            sequence=1,
            input_offset=analysis.input_size,
            record_count=len(evidence),
        )
        summary = FileAnalysis(
            file_type="csv",
            record_count=len(evidence),
            reason=ERROR_STRUCTURE
            if analysis.input_path.name == "rejected.csv"
            else None,
        )
        artifact = write_step_result(connection, analysis, summary, encryption_key=key)
        complete_task(connection, analysis, result=artifact)
        analysis_ids[analysis.input_path.name] = analysis.task_id
    return run, analysis_ids
