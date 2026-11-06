"""Freeze cross-file identity and cohort decisions after the analysis barrier."""

import sqlite3

from redactor.identity.resolution import resolve_sources
from redactor.persistence.files.results import write_step_result
from redactor.persistence.identities.snapshots import build_identity_snapshot
from redactor.persistence.identities.sources import initialize_resolution
from redactor.persistence.runs.inventory import file_step
from redactor.persistence.runs.manifests import read_manifest
from redactor.schemas.persistence import Artifact, Task
from redactor.schemas.pipeline import StepResult
from redactor.utils.configuration import key_fingerprint
from redactor.utils.constants import STEP_ANALYZE, STEP_RESOLVE
from redactor.utils.errors import ERROR_RUN_CONTEXT


def resolve_task(
    connection: sqlite3.Connection, task: Task, *, mapping_key: bytes
) -> StepResult:
    if task.step != STEP_RESOLVE or task.processing_version != task.input_sha256:
        raise ValueError(ERROR_RUN_CONTEXT)
    manifest_artifact = Artifact(
        path=task.input_path, sha256=task.input_sha256, size=task.input_size
    )
    manifest = read_manifest(manifest_artifact, key_fingerprint(mapping_key))
    analysis_task_ids = tuple(
        file_step(connection, manifest_artifact, source, STEP_ANALYZE).task_id
        for source in manifest.files
    )
    sources = initialize_resolution(connection, task, analysis_task_ids, mapping_key)
    resolve_sources(connection, task, sources, mapping_key)
    snapshot = build_identity_snapshot(
        connection, task, mapping_key, manifest.settings.policy.maximum_date_shift_days
    )
    artifact = write_step_result(connection, task, snapshot, encryption_key=mapping_key)
    return StepResult(artifact=artifact)
