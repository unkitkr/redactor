"""Bind verification policy to the accepted run and identity snapshot."""

import sqlite3

from redactor.persistence.files.registration import prepare_successor
from redactor.persistence.files.results import read_step_result
from redactor.schemas.analysis import FileAnalysis
from redactor.schemas.formats import FileInspection
from redactor.schemas.identity import IdentitySnapshot
from redactor.schemas.persistence import Task
from redactor.schemas.verification import VerificationContext
from redactor.utils.constants import IMAGE_FORMATS, STEP_ANALYZE, STEP_INSPECT


def verification_context(
    connection: sqlite3.Connection,
    task: Task,
    resolution_task_id: str,
    mapping_key: bytes,
    *,
    has_pixels: bool | None = None,
) -> VerificationContext:
    if has_pixels is None:
        inspection = read_step_result(
            connection,
            prepare_successor(connection, task, STEP_INSPECT).task_id,
            FileInspection,
            encryption_key=mapping_key,
        )
        has_pixels = inspection.file_type in IMAGE_FORMATS
        if not has_pixels:
            analysis = read_step_result(
                connection,
                prepare_successor(connection, task, STEP_ANALYZE).task_id,
                FileAnalysis,
                encryption_key=mapping_key,
            )
            has_pixels = bool(analysis.embedded_images)
    snapshot = read_step_result(
        connection, resolution_task_id, IdentitySnapshot, encryption_key=mapping_key
    )
    return VerificationContext(
        original_sha256=task.input_sha256,
        identity_sha256=snapshot.digest,
        policy_sha256=task.processing_version,
        has_pixels=has_pixels,
    )
