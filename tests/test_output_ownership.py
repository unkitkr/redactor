"""Never mix a new verifier policy's report with older published files."""

import sqlite3
from pathlib import Path

import pytest

from redactor.coordinator.bootstrap import collect_inventory, prepare_run
from redactor.persistence.runs.manifests import persist_manifest
from redactor.persistence.runs.outputs import bind_output_directory
from redactor.schemas.configuration import PipelineSettings
from redactor.utils.errors import ERROR_OUTPUT_CONFLICT


def test_output_directory_is_bound_before_work_and_replays_only_its_run(
    connection: sqlite3.Connection, tmp_path: Path
) -> None:
    source = tmp_path / "input"
    source.mkdir()
    (source / "records.csv").write_text("patient,mrn\nLena Moreau,00019\n")
    settings = PipelineSettings()
    key = bytes(range(32))
    first = prepare_run(connection, source, settings, key)
    bind_output_directory(connection, first.manifest)
    assert prepare_run(connection, source, settings, key) == first
    bind_output_directory(connection, first.manifest)
    output = tmp_path / "output"
    published = output / "published/records.csv"
    published.parent.mkdir()
    published.write_bytes(b"older result must remain unchanged")

    changed = collect_inventory(source, settings, key).model_copy(
        update={"pipeline_version": "different-verifier-policy"}
    )
    manifest = persist_manifest(connection, changed)
    with pytest.raises(ValueError, match=ERROR_OUTPUT_CONFLICT):
        bind_output_directory(connection, manifest)
    assert published.read_bytes() == b"older result must remain unchanged"
    assert not (output / "report.json").exists()

    # Output predating this ownership contract cannot silently acquire a new
    # policy identity. An explicit fresh workspace is required.
    (output / ".run-id").unlink()
    with pytest.raises(ValueError, match=ERROR_OUTPUT_CONFLICT):
        bind_output_directory(connection, first.manifest)
    assert published.read_bytes() == b"older result must remain unchanged"
