"""Registration helpers for durable file processing."""

import hashlib
import json
import os
import sqlite3
from collections.abc import Sequence
from pathlib import Path

from redactor.persistence.database import state_directory
from redactor.persistence.files.hashing import file_version, hash_stream
from redactor.persistence.queue.tasks import enqueue_task
from redactor.schemas.persistence import Task, TaskSpec
from redactor.utils.constants import (
    JSON_SEPARATORS,
    OUTPUT_DIRECTORY,
    PUBLISHED_DIRECTORY,
    READ_BINARY,
    TEMPORARY_DIRECTORY,
    TEXT_ENCODING,
)
from redactor.utils.errors import ERROR_INPUT_CHANGED


def prepare_task(input_path: Path, step: str, processing_version: str) -> TaskSpec:
    """Fingerprint an immutable input outside the queue's write transaction."""
    resolved_path = input_path.resolve(strict=True)
    with resolved_path.open(READ_BINARY) as stream:
        before = os.fstat(stream.fileno())
        input_sha256 = hash_stream(stream)
        original_version = file_version(before)
        if (
            file_version(os.fstat(stream.fileno())) != original_version
            or file_version(resolved_path.stat()) != original_version
        ):
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


def prepare_successor(
    connection: sqlite3.Connection, source: TaskSpec, step: str
) -> TaskSpec:
    """Reuse an inventoried fingerprint instead of rereading a large input file."""
    identity = json.dumps(
        (str(source.input_path), source.input_sha256, step, source.processing_version),
        separators=JSON_SEPARATORS,
    ).encode(TEXT_ENCODING)
    task_id = hashlib.sha256(identity).hexdigest()
    return TaskSpec(
        task_id=task_id,
        input_path=source.input_path,
        input_sha256=source.input_sha256,
        input_size=source.input_size,
        step=step,
        processing_version=source.processing_version,
        temporary_directory=state_directory(connection) / TEMPORARY_DIRECTORY / task_id,
        output_path=source.output_path,
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
