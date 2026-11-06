"""Publish only completed verification evidence for an accepted rewrite artifact."""

import sqlite3

from redactor.persistence.database import transaction
from redactor.persistence.files.artifacts import install_artifact
from redactor.persistence.files.results import accepted_artifact, read_step_result
from redactor.persistence.queue.tasks import get_task, require_attempt
from redactor.schemas.persistence import Artifact, Task
from redactor.schemas.verification import VerificationContext, VerificationVerdict
from redactor.utils.constants import STEP_PUBLISH, STEP_REWRITE, STEP_VERIFY
from redactor.utils.errors import (
    ERROR_FILE_NOT_REGISTERED,
    ERROR_VERIFICATION_CONTEXT,
)
from redactor.verification.verdict import require_passing_verdict


def publish_verified_artifact(
    connection: sqlite3.Connection,
    claimed: Task,
    verification_task_id: str,
    expected_context: VerificationContext,
) -> Artifact:
    """Record intent before installation; a new attempt can reconcile that intent.

    Accepted source artifacts remain available until terminal cleanup. The caller
    commits task completion after this function returns, leaving a recoverable
    boundary between filesystem installation and SQLite acknowledgement.
    """
    current = require_attempt(connection, claimed)
    verification_task = get_task(connection, verification_task_id)
    verdict = read_step_result(connection, verification_task_id, VerificationVerdict)
    producer = get_task(connection, verdict.producer_task_id)
    dependency = connection.execute(
        "SELECT 1 FROM dependencies WHERE task_id = ? AND depends_on = ?",
        (current.task_id, verification_task_id),
    ).fetchone()
    if (
        current.step != STEP_PUBLISH
        or verification_task.step != STEP_VERIFY
        or producer.step != STEP_REWRITE
        or dependency is None
        or verdict.context != expected_context
        or expected_context.original_sha256 != current.input_sha256
        or producer.input_sha256 != current.input_sha256
        or verification_task.input_sha256 != current.input_sha256
        or producer.processing_version != current.processing_version
        or verification_task.processing_version != current.processing_version
        or accepted_artifact(connection, producer.task_id) != verdict.artifact
    ):
        raise ValueError(ERROR_VERIFICATION_CONTEXT)
    require_passing_verdict(verdict)
    if current.output_path is None:
        raise ValueError(ERROR_FILE_NOT_REGISTERED)

    intent = (
        verification_task_id,
        producer.task_id,
        str(current.output_path),
        verdict.artifact.sha256,
        verdict.artifact.size,
    )
    with transaction(connection):
        require_attempt(connection, claimed)
        previous = connection.execute(
            """
            SELECT verification_task_id, producer_task_id, output_path,
                   artifact_sha256, artifact_size
            FROM publication_intents WHERE task_id = ?
            """,
            (current.task_id,),
        ).fetchone()
        if previous is not None and tuple(previous) != intent:
            raise ValueError(ERROR_VERIFICATION_CONTEXT)
        connection.execute(
            """
            INSERT INTO publication_intents (
                task_id, verification_task_id, producer_task_id, output_path,
                artifact_sha256, artifact_size
            ) VALUES (?, ?, ?, ?, ?, ?) ON CONFLICT(task_id) DO NOTHING
            """,
            (current.task_id, *intent),
        )

    return install_artifact(verdict.artifact, current.output_path)
