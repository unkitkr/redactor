"""Bind verification policy to the accepted run and identity snapshot."""

import sqlite3

from redactor.persistence.files.results import read_step_result
from redactor.schemas.identity import IdentitySnapshot
from redactor.schemas.persistence import Task
from redactor.schemas.verification import VerificationContext


def verification_context(
    connection: sqlite3.Connection,
    task: Task,
    resolution_task_id: str,
    mapping_key: bytes,
    *,
    has_pixels: bool = False,
) -> VerificationContext:
    snapshot = read_step_result(
        connection, resolution_task_id, IdentitySnapshot, encryption_key=mapping_key
    )
    return VerificationContext(
        original_sha256=task.input_sha256,
        identity_sha256=snapshot.digest,
        policy_sha256=task.processing_version,
        has_pixels=has_pixels,
    )
