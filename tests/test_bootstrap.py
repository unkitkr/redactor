"""Integration coverage for a frozen inventory and global evidence barrier."""

import sqlite3
from pathlib import Path

import pytest

from redactor.coordinator.bootstrap import prepare_run
from redactor.persistence.manifests import read_manifest
from redactor.persistence.queue import (
    claim_task,
    complete_task,
    iter_tasks,
    recover_interrupted,
)
from redactor.schemas.configuration import PipelineSettings
from redactor.utils.configuration import key_fingerprint
from redactor.utils.constants import (
    STEP_ANALYZE,
    STEP_INSPECT,
    STEP_RESOLVE,
)
from redactor.utils.errors import ERROR_RUN_CONTEXT


def test_frozen_inventory_replays_and_waits_for_every_analysis(
    connection: sqlite3.Connection, tmp_path: Path
) -> None:
    input_directory = tmp_path / "input"
    first_directory = input_directory / "first"
    second_directory = input_directory / "second"
    first_directory.mkdir(parents=True)
    second_directory.mkdir()
    (first_directory / "records.csv").write_text("code,value\nA,1\n")
    (second_directory / "records.csv").write_text("code,value\nB,2\n")
    key = bytes(range(32))
    settings = PipelineSettings()
    run = prepare_run(connection, input_directory, settings, key)
    manifest = read_manifest(run.manifest, key_fingerprint(key))
    assert len(manifest.files) == 2
    tasks = list(iter_tasks(connection))
    assert len(tasks) == 5
    output_paths = {task.output_path for task in tasks if task.step == STEP_INSPECT}
    assert output_paths == {
        tmp_path / "output" / "published" / "first" / "records.csv",
        tmp_path / "output" / "published" / "second" / "records.csv",
    }
    assert claim_task(connection, step=STEP_RESOLVE) is None

    inspection = claim_task(connection, step=STEP_INSPECT)
    assert inspection is not None
    # Startup can register the same graph after an interrupted worker attempt.
    recover_interrupted(connection)
    disabled = settings.model_copy(
        update={"remote": settings.remote.model_copy(update={"enabled": False})}
    )
    assert prepare_run(connection, input_directory, disabled, key) == run
    assert len(list(iter_tasks(connection))) == 5

    for _ in manifest.files:
        inspection = claim_task(connection, step=STEP_INSPECT)
        assert inspection is not None
        complete_task(connection, inspection)
        analysis = claim_task(connection, step=STEP_ANALYZE)
        assert analysis is not None
        assert claim_task(connection, step=STEP_RESOLVE) is None
        complete_task(connection, analysis)
    resolution = claim_task(connection, step=STEP_RESOLVE)
    assert resolution is not None
    assert resolution.task_id == run.resolution_task_id
    complete_task(connection, resolution)
    assert prepare_run(connection, input_directory, settings, key) == run
    assert claim_task(connection, processing_version=run.manifest.sha256) is None


def test_inventory_key_policy_and_source_changes_get_distinct_run_identities(
    connection: sqlite3.Connection, tmp_path: Path
) -> None:
    input_directory = tmp_path / "input"
    input_directory.mkdir()
    source = input_directory / "records.csv"
    source.write_text("code,value\nA,1\n")
    settings = PipelineSettings()
    key = bytes(range(32))
    original = prepare_run(connection, input_directory, settings, key)
    new_key = bytes(reversed(key))
    with pytest.raises(ValueError, match=ERROR_RUN_CONTEXT):
        read_manifest(original.manifest, key_fingerprint(new_key))
    changed_key = prepare_run(connection, input_directory, settings, new_key)
    changed_policy = settings.model_copy(
        update={
            "policy": settings.policy.model_copy(update={"maximum_date_shift_days": 30})
        }
    )
    changed_settings = prepare_run(connection, input_directory, changed_policy, key)
    source.write_text("code,value\nA,2\n")
    changed_source = prepare_run(connection, input_directory, settings, key)
    assert (
        len(
            {
                original.manifest.sha256,
                changed_key.manifest.sha256,
                changed_settings.manifest.sha256,
                changed_source.manifest.sha256,
            }
        )
        == 4
    )
