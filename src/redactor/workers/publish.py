"""Publish exact verified bytes and persist the terminal receipt."""

import sqlite3

from redactor.persistence.files.publication import publish_verified_artifact
from redactor.persistence.files.registration import prepare_successor
from redactor.persistence.files.results import write_step_result
from redactor.schemas.outcomes import FileOutcome
from redactor.schemas.persistence import Task
from redactor.schemas.pipeline import StepResult
from redactor.utils.constants import OUTCOME_PUBLISHED, STEP_VERIFY
from redactor.verification.context import verification_context


def publish_task(
    connection: sqlite3.Connection,
    task: Task,
    *,
    mapping_key: bytes,
    resolution_task_id: str,
) -> StepResult:
    context = verification_context(connection, task, resolution_task_id, mapping_key)
    verified = prepare_successor(connection, task, STEP_VERIFY)
    artifact = publish_verified_artifact(connection, task, verified.task_id, context)
    return StepResult(
        artifact=write_step_result(
            connection,
            task,
            FileOutcome(status=OUTCOME_PUBLISHED, artifact=artifact),
            encryption_key=mapping_key,
        )
    )
