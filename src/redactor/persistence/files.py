"""File registration and bounded-memory artifact persistence."""

import hashlib
import json
import os
import sqlite3
from collections.abc import Sequence
from pathlib import Path
from typing import BinaryIO

from redactor.persistence.database import state_directory
from redactor.persistence.queue import enqueue_task
from redactor.schemas.persistence import Task, TaskSpec
from redactor.utils.constants import (
    ERROR_ARTIFACT_CORRUPT,
    ERROR_INPUT_CHANGED,
    HASH_CHUNK_BYTES,
    JSON_SEPARATORS,
    OUTPUT_DIRECTORY,
    PUBLISHED_DIRECTORY,
    READ_BINARY,
    TEMPORARY_DIRECTORY,
    TEXT_ENCODING,
)


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
