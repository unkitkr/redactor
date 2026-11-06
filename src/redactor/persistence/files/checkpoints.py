"""Persist complete-record progress and recover a fenced attempt's working file."""

import json
import os
import sqlite3
from pathlib import Path

from redactor.persistence.database import transaction
from redactor.persistence.files.artifacts import temporary_path_for
from redactor.persistence.files.hashing import hash_stream
from redactor.persistence.queue.tasks import require_attempt
from redactor.schemas.persistence import Checkpoint, Task
from redactor.utils.constants import JSON_SEPARATORS, PRIVATE_FILE_MODE
from redactor.utils.errors import (
    ERROR_ARTIFACT_CORRUPT,
    ERROR_ARTIFACT_MISSING,
    ERROR_INVALID_CHECKPOINT,
)
from redactor.utils.filesystem import sync_directory


def latest_checkpoint(
    connection: sqlite3.Connection, task_id: str
) -> Checkpoint | None:
    row = connection.execute(
        "SELECT * FROM checkpoints WHERE task_id = ? ORDER BY sequence DESC LIMIT 1",
        (task_id,),
    ).fetchone()
    if row is None:
        return None
    values = dict(row)
    values["counts"] = json.loads(values.pop("counts_json"))
    values["cursor"] = json.loads(values.pop("cursor_json"))
    return Checkpoint.model_validate(values)


def save_checkpoint(
    connection: sqlite3.Connection, claimed: Task, checkpoint: Checkpoint
) -> None:
    """Sync bytes, then accept progress from the current attempt only.

    The writer supplies its incremental SHA-256 of the committed prefix. Rehashing
    every prefix here would make a large streaming write quadratic. Recovery
    independently checks that digest before it permits resumption.
    """
    current = require_attempt(connection, claimed)
    if (
        checkpoint.task_id != current.task_id
        or checkpoint.artifact_path != temporary_path_for(current)
        or checkpoint.input_offset > current.input_size
    ):
        raise ValueError(ERROR_INVALID_CHECKPOINT)

    descriptor = _open_working_file(checkpoint.artifact_path)
    try:
        if os.fstat(descriptor).st_size < checkpoint.output_offset:
            raise ValueError(ERROR_INVALID_CHECKPOINT)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    sync_directory(checkpoint.artifact_path.parent)

    with transaction(connection):
        require_attempt(connection, claimed)
        previous = latest_checkpoint(connection, current.task_id)
        if previous == checkpoint:
            return
        expected_sequence = 1 if previous is None else previous.sequence + 1
        if checkpoint.sequence != expected_sequence or (
            previous is not None
            and (
                checkpoint.adapter_version != previous.adapter_version
                or checkpoint.input_offset < previous.input_offset
                or checkpoint.output_offset < previous.output_offset
                or checkpoint.record_count < previous.record_count
                or any(
                    checkpoint.counts.get(kind, 0) < count
                    for kind, count in previous.counts.items()
                )
            )
        ):
            raise ValueError(ERROR_INVALID_CHECKPOINT)
        connection.execute(
            """
            INSERT INTO checkpoints (
                task_id, sequence, artifact_path, input_offset, output_offset,
                record_count, output_prefix_sha256, counts_json,
                adapter_version, cursor_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                checkpoint.task_id,
                checkpoint.sequence,
                str(checkpoint.artifact_path),
                checkpoint.input_offset,
                checkpoint.output_offset,
                checkpoint.record_count,
                checkpoint.output_prefix_sha256,
                json.dumps(checkpoint.counts, separators=JSON_SEPARATORS),
                checkpoint.adapter_version,
                json.dumps(checkpoint.cursor, separators=JSON_SEPARATORS),
            ),
        )


def resume_checkpoint(
    connection: sqlite3.Connection, claimed: Task, adapter_version: str
) -> Checkpoint | None:
    """Adopt committed bytes after exclusive startup recovery fences the old worker.

    A hard link avoids copying a multi-gigabyte prefix. Old checkpoint paths stay
    valid until terminal cleanup. Only the newest checkpoint permits appending;
    any uncommitted suffix is truncated before returning to the writer.
    """
    current = require_attempt(connection, claimed)
    checkpoint = latest_checkpoint(connection, current.task_id)
    if checkpoint is None:
        return None
    working_path = temporary_path_for(current)
    if (
        checkpoint.adapter_version != adapter_version
        or checkpoint.input_offset > current.input_size
        or checkpoint.artifact_path.parent != working_path.parent
    ):
        raise ValueError(ERROR_INVALID_CHECKPOINT)

    descriptor = _open_working_file(checkpoint.artifact_path)
    with os.fdopen(descriptor, "r+b") as stream:
        if hash_stream(stream, checkpoint.output_offset) != (
            checkpoint.output_prefix_sha256
        ):
            raise ValueError(ERROR_ARTIFACT_CORRUPT)
        require_attempt(connection, claimed)
        if working_path != checkpoint.artifact_path:
            try:
                os.link(checkpoint.artifact_path, working_path, follow_symlinks=False)
            except FileExistsError:
                if working_path.is_symlink() or not working_path.samefile(
                    checkpoint.artifact_path
                ):
                    raise ValueError(ERROR_ARTIFACT_CORRUPT) from None
            sync_directory(working_path.parent)
        stream.truncate(checkpoint.output_offset)
        stream.flush()
        os.fsync(stream.fileno())
    return checkpoint.model_copy(update={"artifact_path": working_path})


def _open_working_file(path: Path) -> int:
    try:
        descriptor = os.open(path, os.O_RDWR | os.O_NOFOLLOW)
    except FileNotFoundError:
        raise ValueError(ERROR_ARTIFACT_MISSING) from None
    os.fchmod(descriptor, PRIVATE_FILE_MODE)
    return descriptor
