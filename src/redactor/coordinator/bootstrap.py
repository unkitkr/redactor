"""Freeze discovery and register the evidence barrier before starting workers."""

import sqlite3
from pathlib import Path

from redactor.coordinator.inventory import iter_input_files
from redactor.persistence.files.registration import prepare_successor, prepare_task
from redactor.persistence.queue.tasks import enqueue_task
from redactor.persistence.runs.inventory import file_step
from redactor.persistence.runs.manifests import persist_manifest
from redactor.schemas.configuration import PipelineSettings
from redactor.schemas.inventory import InventoryFile, PreparedRun, RunManifest
from redactor.utils.configuration import key_fingerprint, processing_fingerprint
from redactor.utils.constants import (
    MAX_MANIFEST_BYTES,
    STEP_ANALYZE,
    STEP_INSPECT,
    STEP_RESOLVE,
    TEXT_ENCODING,
)
from redactor.utils.errors import ERROR_INVENTORY_LIMIT


def prepare_run(
    connection: sqlite3.Connection,
    input_directory: Path,
    settings: PipelineSettings,
    mapping_key: bytes,
) -> PreparedRun:
    """Restart discovery safely; no worker sees a partially registered inventory."""
    manifest = collect_inventory(input_directory, settings, mapping_key)
    artifact = persist_manifest(connection, manifest)
    analysis_tasks: list[str] = []
    for source in manifest.files:
        inspection = file_step(connection, artifact, source, STEP_INSPECT)
        enqueue_task(connection, inspection)
        analysis = prepare_successor(connection, inspection, STEP_ANALYZE)
        enqueue_task(connection, analysis, dependencies=(inspection.task_id,))
        analysis_tasks.append(analysis.task_id)

    resolution = prepare_task(artifact.path, STEP_RESOLVE, artifact.sha256)
    resolution = prepare_successor(connection, resolution, STEP_RESOLVE)
    enqueue_task(connection, resolution, dependencies=analysis_tasks)
    return PreparedRun(manifest=artifact, resolution_task_id=resolution.task_id)


def collect_inventory(
    input_directory: Path, settings: PipelineSettings, mapping_key: bytes
) -> RunManifest:
    input_directory = input_directory.resolve(strict=True)
    files: list[InventoryFile] = []
    serialized_size = 0
    version = processing_fingerprint(settings)
    for path in iter_input_files(input_directory):
        fingerprint = prepare_task(path, STEP_INSPECT, version)
        source = InventoryFile(
            input_path=fingerprint.input_path,
            relative_path=fingerprint.input_path.relative_to(input_directory),
            sha256=fingerprint.input_sha256,
            size=fingerprint.input_size,
        )
        serialized_size += len(source.model_dump_json().encode(TEXT_ENCODING))
        if serialized_size > MAX_MANIFEST_BYTES:
            raise ValueError(ERROR_INVENTORY_LIMIT)
        files.append(source)

    # Availability may change on recovery; it is not part of processing identity.
    frozen_settings = settings.model_copy(
        update={"remote": settings.remote.model_copy(update={"enabled": True})}
    )
    return RunManifest(
        input_directory=input_directory,
        files=tuple(sorted(files, key=lambda source: source.relative_path.as_posix())),
        settings=frozen_settings,
        key_fingerprint=key_fingerprint(mapping_key),
    )
