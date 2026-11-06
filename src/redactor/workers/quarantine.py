"""Retain rejected originals with an atomic, PHI-free reason sidecar."""

import shutil
import sqlite3

from redactor.persistence.database import state_directory
from redactor.persistence.files.artifacts import (
    create_temporary_file,
    inspect_artifact,
    install_artifact,
)
from redactor.persistence.files.registration import prepare_successor
from redactor.persistence.files.results import read_step_result, write_step_result
from redactor.schemas.analysis import FileAnalysis
from redactor.schemas.outcomes import FileFailure, FileOutcome
from redactor.schemas.persistence import Task
from redactor.schemas.pipeline import StepResult
from redactor.schemas.verification import VerificationVerdict
from redactor.utils.constants import (
    HASH_CHUNK_BYTES,
    OUTCOME_QUARANTINED,
    OUTPUT_DIRECTORY,
    PUBLISHED_DIRECTORY,
    QUARANTINE_DIRECTORY,
    REASON_FILE_SUFFIX,
    STEP_ANALYZE,
    STEP_REWRITE,
    STEP_VERIFY,
)
from redactor.utils.errors import (
    ERROR_FILE_NOT_REGISTERED,
    ERROR_INPUT_CHANGED,
    ERROR_VERIFICATION,
)


def quarantine_reason(
    connection: sqlite3.Connection, task: Task, mapping_key: bytes
) -> FileFailure:
    analysis = read_step_result(
        connection,
        prepare_successor(connection, task, STEP_ANALYZE).task_id,
        FileAnalysis,
        encryption_key=mapping_key,
    )
    if analysis.reason is not None:
        return FileFailure(step=STEP_ANALYZE, reason=analysis.reason)
    parents = connection.execute(
        "SELECT tasks.* FROM dependencies JOIN tasks ON tasks.task_id = depends_on "
        "WHERE dependencies.task_id = ?",
        (task.task_id,),
    ).fetchall()
    for parent in parents:
        if parent["step"] == STEP_REWRITE:
            return read_step_result(
                connection,
                parent["task_id"],
                FileFailure,
                encryption_key=mapping_key,
            )
        if parent["step"] == STEP_VERIFY:
            verdict = read_step_result(
                connection, parent["task_id"], VerificationVerdict
            )
            reason = next(
                (check.reason_code for check in verdict.checks if check.reason_code),
                ERROR_VERIFICATION,
            )
            return FileFailure(step=STEP_VERIFY, reason=reason)
    raise ValueError(ERROR_VERIFICATION)


def quarantine_task(
    connection: sqlite3.Connection, task: Task, *, mapping_key: bytes
) -> StepResult:
    failure = quarantine_reason(connection, task, mapping_key)
    if task.output_path is None:
        raise ValueError(ERROR_FILE_NOT_REGISTERED)
    output_root = state_directory(connection).parent / OUTPUT_DIRECTORY
    relative = task.output_path.relative_to(output_root / PUBLISHED_DIRECTORY)
    destination = output_root / QUARANTINE_DIRECTORY / relative
    path = create_temporary_file(connection, task)
    with task.input_path.open("rb") as source, path.open("wb") as staged:
        shutil.copyfileobj(source, staged, HASH_CHUNK_BYTES)
    original = inspect_artifact(path, persist=True)
    if original.sha256 != task.input_sha256 or original.size != task.input_size:
        raise ValueError(ERROR_INPUT_CHANGED)
    quarantined = install_artifact(original, destination)
    reason_artifact = write_step_result(connection, task, failure, auxiliary=True)
    install_artifact(
        reason_artifact, destination.with_name(destination.name + REASON_FILE_SUFFIX)
    )
    # The reason hard link must stay immutable when the terminal receipt is saved.
    reason_artifact.path.unlink()
    return StepResult(
        artifact=write_step_result(
            connection,
            task,
            FileOutcome(
                status=OUTCOME_QUARANTINED, reason=failure.reason, artifact=quarantined
            ),
            encryption_key=mapping_key,
            auxiliary=True,
        )
    )
