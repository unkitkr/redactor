"""File registration and bounded-memory artifact persistence."""

import hashlib
import json
import os
import sqlite3
from collections.abc import Sequence
from errno import EXDEV
from pathlib import Path
from typing import BinaryIO

from redactor.persistence.database import state_directory
from redactor.persistence.queue import enqueue_task, require_attempt
from redactor.schemas.persistence import Artifact, Task, TaskSpec
from redactor.utils.constants import (
    HASH_CHUNK_BYTES,
    JSON_SEPARATORS,
    OUTPUT_DIRECTORY,
    PRIVATE_FILE_MODE,
    PUBLISHED_DIRECTORY,
    READ_BINARY,
    TEMPORARY_DIRECTORY,
    TEMPORARY_FILE_TEMPLATE,
    TEXT_ENCODING,
)
from redactor.utils.errors import (
    ERROR_ARTIFACT_CORRUPT,
    ERROR_ARTIFACT_MISSING,
    ERROR_FILE_NOT_REGISTERED,
    ERROR_INPUT_CHANGED,
    ERROR_OUTPUT_CONFLICT,
    ERROR_OUTPUT_FILESYSTEM,
)
from redactor.utils.filesystem import private_directory, sync_directory


def prepare_task(input_path: Path, step: str, processing_version: str) -> TaskSpec:
    """Fingerprint an immutable input outside the queue's write transaction."""
    resolved_path = input_path.resolve(strict=True)
    with resolved_path.open(READ_BINARY) as stream:
        before = os.fstat(stream.fileno())
        input_sha256 = hash_stream(stream)
        if _file_version(os.fstat(stream.fileno())) != _file_version(
            before
        ) or _file_version(resolved_path.stat()) != _file_version(before):
            raise ValueError(ERROR_INPUT_CHANGED)

    identity = json.dumps(
        (str(resolved_path), input_sha256, step, processing_version),
        separators=JSON_SEPARATORS,
    ).encode(TEXT_ENCODING)
    return TaskSpec(
        task_id=hashlib.sha256(identity).hexdigest(),
        input_path=resolved_path,
        input_sha256=input_sha256,
        input_size=before.st_size,
        step=step,
        processing_version=processing_version,
    )


def register_file(
    connection: sqlite3.Connection,
    input_path: Path,
    step: str,
    processing_version: str,
    *,
    dependencies: Sequence[str] = (),
) -> Task:
    """Register one file step and its locations in a single idempotent commit.

    Paths are recorded without creating artifacts. Output retains the input name;
    callers must independently verify an artifact before finalizing it there.
    """
    spec = prepare_task(input_path, step, processing_version)
    state = state_directory(connection)
    spec = spec.model_copy(
        update={
            "temporary_directory": state / TEMPORARY_DIRECTORY / spec.task_id,
            "output_path": (
                state.parent
                / OUTPUT_DIRECTORY
                / PUBLISHED_DIRECTORY
                / spec.input_path.name
            ),
        }
    )
    return enqueue_task(connection, spec, dependencies=dependencies)


def create_temporary_file(connection: sqlite3.Connection, claimed: Task) -> Path:
    """Create a private file for this attempt without truncating existing bytes.

    Reopening a partial file does not make it safe to append: checkpoint recovery
    will determine the usable prefix in a separate milestone.
    """
    current = require_attempt(connection, claimed)
    temporary_path = _temporary_path(current)
    private_directory(temporary_path.parent)
    descriptor = os.open(
        temporary_path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, PRIVATE_FILE_MODE
    )
    try:
        os.fchmod(descriptor, PRIVATE_FILE_MODE)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    sync_directory(temporary_path.parent)
    return temporary_path


def seal_temporary_file(connection: sqlite3.Connection, claimed: Task) -> Artifact:
    """Sync and fingerprint a closed temporary file before independent verification.

    The writer must be closed before this call and the bytes must remain unchanged
    through verification and finalization. This function does not check for PHI.
    """
    current = require_attempt(connection, claimed)
    return _inspect_artifact(_temporary_path(current), persist=True)


def finalize_output(
    connection: sqlite3.Connection, claimed: Task, verified: Artifact
) -> Artifact:
    """Install the exact independently verified bytes at the registered output path.

    Only call after verification succeeds. Artifact metadata is a byte-integrity
    check, not proof of clinical safety. The coordinator must serialize this with
    recovery and stop old writers first. No database write transaction is held
    during filesystem I/O, and task completion remains an explicit separate call.

    An atomic hard link prevents replacement of an existing conflicting output.
    Temporary and output directories must be on the same local filesystem.
    """
    current = require_attempt(connection, claimed)
    temporary_path = _temporary_path(current)
    output_path = current.output_path
    assert output_path is not None
    if verified.path != temporary_path:
        raise ValueError(ERROR_ARTIFACT_CORRUPT)

    if not temporary_path.exists():
        # A previous call may have installed the output and removed the temp file
        # before the process died or the caller recorded task completion.
        output = _inspect_artifact(output_path, persist=True)
        _require_matching_bytes(output, verified, ERROR_OUTPUT_CONFLICT)
        sync_directory(output_path.parent)
        sync_directory(temporary_path.parent)
        return output

    staged = _inspect_artifact(temporary_path, persist=True)
    _require_matching_bytes(staged, verified, ERROR_ARTIFACT_CORRUPT)
    private_directory(output_path.parent)
    try:
        os.link(temporary_path, output_path, follow_symlinks=False)
    except FileExistsError:
        output = _inspect_artifact(output_path, persist=True)
        _require_matching_bytes(output, verified, ERROR_OUTPUT_CONFLICT)
    except OSError as error:
        if error.errno == EXDEV:
            raise ValueError(ERROR_OUTPUT_FILESYSTEM) from error
        raise

    sync_directory(output_path.parent)
    temporary_path.unlink()
    sync_directory(temporary_path.parent)
    return Artifact(path=output_path, sha256=verified.sha256, size=verified.size)


def _temporary_path(task: Task) -> Path:
    if task.temporary_directory is None or task.output_path is None:
        raise ValueError(ERROR_FILE_NOT_REGISTERED)
    return task.temporary_directory / TEMPORARY_FILE_TEMPLATE.format(
        attempt_token=task.attempt_token
    )


def _inspect_artifact(path: Path, *, persist: bool) -> Artifact:
    if path.is_symlink():
        raise ValueError(ERROR_ARTIFACT_CORRUPT)
    try:
        with path.open(READ_BINARY) as stream:
            before = os.fstat(stream.fileno())
            if persist:
                os.fsync(stream.fileno())
            digest = hash_stream(stream)
            if _file_version(os.fstat(stream.fileno())) != _file_version(
                before
            ) or _file_version(path.stat()) != _file_version(before):
                raise ValueError(ERROR_ARTIFACT_CORRUPT)
    except FileNotFoundError:
        raise ValueError(ERROR_ARTIFACT_MISSING) from None
    return Artifact(path=path, sha256=digest, size=before.st_size)


def _require_matching_bytes(actual: Artifact, expected: Artifact, code: str) -> None:
    if actual.sha256 != expected.sha256 or actual.size != expected.size:
        raise ValueError(code)


def _file_version(metadata: os.stat_result) -> tuple[int, int, int, int, int]:
    """Compare identity and modification metadata without access-time changes."""
    return (
        metadata.st_dev,
        metadata.st_ino,
        metadata.st_size,
        metadata.st_mtime_ns,
        metadata.st_ctime_ns,
    )


def hash_file(file_path: Path) -> str:
    with file_path.open(READ_BINARY) as stream:
        return hash_stream(stream)


def hash_stream(stream: BinaryIO, length: int | None = None) -> str:
    """Hash from the current position without materializing the file in memory."""
    digest = hashlib.sha256()
    remaining = length

    while remaining is None or remaining > 0:
        chunk_size = (
            HASH_CHUNK_BYTES if remaining is None else min(HASH_CHUNK_BYTES, remaining)
        )
        chunk = stream.read(chunk_size)
        if not chunk:
            if remaining:
                raise ValueError(ERROR_ARTIFACT_CORRUPT)
            break

        digest.update(chunk)
        if remaining is not None:
            remaining -= len(chunk)

    return digest.hexdigest()
