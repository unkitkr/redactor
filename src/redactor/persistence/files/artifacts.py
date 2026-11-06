"""Artifacts helpers for durable file processing."""

import os
import sqlite3
from errno import EXDEV
from pathlib import Path

from redactor.persistence.files.hashing import file_version, hash_stream
from redactor.persistence.queue.tasks import require_attempt
from redactor.schemas.persistence import Artifact, Task
from redactor.utils.constants import (
    PRIVATE_FILE_MODE,
    READ_BINARY,
    RESULT_FILE_TEMPLATE,
    TEMPORARY_FILE_TEMPLATE,
)
from redactor.utils.errors import (
    ERROR_ARTIFACT_CORRUPT,
    ERROR_ARTIFACT_MISSING,
    ERROR_FILE_NOT_REGISTERED,
    ERROR_OUTPUT_CONFLICT,
    ERROR_OUTPUT_FILESYSTEM,
)
from redactor.utils.filesystem import private_directory, sync_directory


def create_temporary_file(
    connection: sqlite3.Connection, claimed: Task, *, result_file: bool = False
) -> Path:
    """Create a private file for this attempt without truncating existing bytes.

    Reopening a partial file does not make it safe to append: checkpoint recovery
    determines the usable prefix before the writer resumes.
    """
    current = require_attempt(connection, claimed)
    temporary_path = temporary_path_for(current, result_file=result_file)
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
    return inspect_artifact(temporary_path_for(current), persist=True)


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
    temporary_path = temporary_path_for(current)
    output_path = current.output_path
    assert output_path is not None
    if verified.path != temporary_path:
        raise ValueError(ERROR_ARTIFACT_CORRUPT)

    published = install_artifact(verified, output_path)
    if temporary_path.exists():
        temporary_path.unlink()
        sync_directory(temporary_path.parent)
    return published


def install_artifact(artifact: Artifact, output_path: Path) -> Artifact:
    """Atomically install exact bytes without overwriting a conflicting result.

    This is a filesystem primitive, not permission to publish clinical content.
    Clinical callers must use persistence.files.publication.publish_verified_artifact.
    """
    if output_path.is_symlink():
        raise ValueError(ERROR_OUTPUT_CONFLICT)
    if output_path.exists():
        output = inspect_artifact(output_path, persist=True)
        _require_matching_bytes(output, artifact, ERROR_OUTPUT_CONFLICT)
        sync_directory(output_path.parent)
        return output

    staged = inspect_artifact(artifact.path, persist=True)
    _require_matching_bytes(staged, artifact, ERROR_ARTIFACT_CORRUPT)
    private_directory(output_path.parent)
    try:
        os.link(artifact.path, output_path, follow_symlinks=False)
    except FileExistsError:
        output = inspect_artifact(output_path, persist=True)
        _require_matching_bytes(output, artifact, ERROR_OUTPUT_CONFLICT)
    except OSError as error:
        if error.errno == EXDEV:
            raise ValueError(ERROR_OUTPUT_FILESYSTEM) from error
        raise

    sync_directory(output_path.parent)
    return Artifact(path=output_path, sha256=artifact.sha256, size=artifact.size)


def temporary_path_for(task: Task, *, result_file: bool = False) -> Path:
    """Locate an attempt's working file, including non-public pipeline artifacts."""
    if task.temporary_directory is None or task.attempt_token is None:
        raise ValueError(ERROR_FILE_NOT_REGISTERED)
    template = RESULT_FILE_TEMPLATE if result_file else TEMPORARY_FILE_TEMPLATE
    return task.temporary_directory / template.format(attempt_token=task.attempt_token)


def inspect_artifact(path: Path, *, persist: bool) -> Artifact:
    if path.is_symlink():
        raise ValueError(ERROR_ARTIFACT_CORRUPT)
    try:
        with path.open(READ_BINARY) as stream:
            before = os.fstat(stream.fileno())
            if persist:
                os.fsync(stream.fileno())
            digest = hash_stream(stream)
            original_version = file_version(before)
            if (
                file_version(os.fstat(stream.fileno())) != original_version
                or file_version(path.stat()) != original_version
            ):
                raise ValueError(ERROR_ARTIFACT_CORRUPT)
    except FileNotFoundError:
        raise ValueError(ERROR_ARTIFACT_MISSING) from None
    return Artifact(path=path, sha256=digest, size=before.st_size)


def _require_matching_bytes(actual: Artifact, expected: Artifact, code: str) -> None:
    if actual.sha256 != expected.sha256 or actual.size != expected.size:
        raise ValueError(code)
