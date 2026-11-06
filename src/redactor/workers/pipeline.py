"""Dispatch one claimed step and accept its artifact and successors together."""

import sqlite3
from collections.abc import Mapping

from redactor.persistence.queue import complete_task, require_attempt
from redactor.schemas.persistence import Task
from redactor.schemas.pipeline import StepHandler
from redactor.utils.errors import ERROR_UNKNOWN_STEP


def execute_task(
    connection: sqlite3.Connection,
    task: Task,
    handlers: Mapping[str, StepHandler],
) -> None:
    require_attempt(connection, task)
    handler = handlers.get(task.step)
    if handler is None:
        raise ValueError(ERROR_UNKNOWN_STEP)
    result = handler(connection, task)
    complete_task(
        connection, task, result=result.artifact, successors=result.successors
    )
