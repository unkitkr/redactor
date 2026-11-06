"""Small structured step results and immutable references to accepted artifacts."""

import hashlib
import sqlite3
from typing import TypeVar

from pydantic import BaseModel, ValidationError

from redactor.persistence.files.artifacts import (
    create_temporary_file,
    inspect_artifact,
)
from redactor.persistence.queue.tasks import get_task
from redactor.schemas.persistence import Artifact, Task
from redactor.utils.constants import MAX_MANIFEST_BYTES, STATUS_SUCCEEDED
from redactor.utils.encryption import decrypt_payload, encrypt_payload
from redactor.utils.errors import ERROR_ARTIFACT_CORRUPT, ERROR_STEP_RESULT

ResultModel = TypeVar("ResultModel", bound=BaseModel)


def write_step_result(
    connection: sqlite3.Connection,
    claimed: Task,
    result: BaseModel,
    *,
    encryption_key: bytes | None = None,
    auxiliary: bool = False,
) -> Artifact:
    payload = result.model_dump_json().encode()
    if encryption_key is not None:
        payload = encrypt_payload(
            encryption_key, payload, context=claimed.task_id.encode()
        )
    if len(payload) > MAX_MANIFEST_BYTES:
        raise ValueError(ERROR_STEP_RESULT)
    path = create_temporary_file(connection, claimed, result_file=auxiliary)
    path.write_bytes(payload)
    return inspect_artifact(path, persist=True)


def accepted_artifact(connection: sqlite3.Connection, task_id: str) -> Artifact:
    task = get_task(connection, task_id)
    if (
        task.status != STATUS_SUCCEEDED
        or task.result_path is None
        or task.result_sha256 is None
        or task.result_size is None
    ):
        raise ValueError(ERROR_STEP_RESULT)
    return Artifact(
        path=task.result_path, sha256=task.result_sha256, size=task.result_size
    )


def read_step_result(
    connection: sqlite3.Connection,
    task_id: str,
    schema: type[ResultModel],
    *,
    encryption_key: bytes | None = None,
) -> ResultModel:
    artifact = accepted_artifact(connection, task_id)
    if artifact.size > MAX_MANIFEST_BYTES:
        raise ValueError(ERROR_STEP_RESULT)
    if artifact.path.is_symlink():
        raise ValueError(ERROR_ARTIFACT_CORRUPT)
    with artifact.path.open("rb") as stream:
        payload = stream.read(MAX_MANIFEST_BYTES + 1)
    if len(payload) != artifact.size or hashlib.sha256(payload).hexdigest() != (
        artifact.sha256
    ):
        raise ValueError(ERROR_ARTIFACT_CORRUPT)
    if encryption_key is not None:
        payload = decrypt_payload(encryption_key, payload, context=task_id.encode())
    try:
        return schema.model_validate_json(payload)
    except ValidationError:
        raise ValueError(ERROR_STEP_RESULT) from None
