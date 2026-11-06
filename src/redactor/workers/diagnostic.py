"""The original diagnostic step, kept separate from clinical processing."""

import os
import sqlite3

from redactor.schemas.persistence import Task
from redactor.schemas.pipeline import StepResult
from redactor.schemas.worker import TaskSummary


def print_task(connection: sqlite3.Connection, task: Task) -> StepResult:
    summary = TaskSummary(
        task_id=task.task_id,
        step=task.step,
        attempt_count=task.attempt_count,
        worker_pid=os.getpid(),
    )
    print(summary.model_dump_json(), flush=True)
    return StepResult()
