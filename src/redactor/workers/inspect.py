"""Persist inspection outcomes so rejected files can still settle the barrier."""

import sqlite3

from redactor.formats.inspection import inspect_file
from redactor.persistence.files.artifacts import inspect_artifact
from redactor.persistence.files.hashing import file_version
from redactor.persistence.files.results import write_step_result
from redactor.schemas.configuration import ResourceSettings
from redactor.schemas.persistence import Task
from redactor.schemas.pipeline import StepResult
from redactor.utils.errors import ERROR_INPUT_CHANGED


def inspect_task(
    connection: sqlite3.Connection,
    task: Task,
    *,
    resources: ResourceSettings,
    mapping_key: bytes,
) -> StepResult:
    before = file_version(task.input_path.stat())
    source = inspect_artifact(task.input_path, persist=False)
    if source.sha256 != task.input_sha256 or source.size != task.input_size:
        raise ValueError(ERROR_INPUT_CHANGED)
    result = inspect_file(task.input_path, resources)
    if file_version(task.input_path.stat()) != before:
        raise ValueError(ERROR_INPUT_CHANGED)
    # Headers can themselves contain identifiers, so inspection evidence is private.
    artifact = write_step_result(connection, task, result, encryption_key=mapping_key)
    return StepResult(artifact=artifact)
