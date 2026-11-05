"""Drain ready placeholder tasks through a process-local SQLite connection."""

import os
from pathlib import Path

from redactor.persistence.client import claim_task, complete_task, open_queue
from redactor.schemas.worker import TaskSummary
from redactor.utils.constants import BOOTSTRAP_PROCESSING_VERSION, PRINT_TASK_STEP


def consume_tasks(state_directory: Path, coordinator_pid: int) -> None:
    """Print safe task metadata and acknowledge this diagnostic step only.

    Inventory is complete before workers start, so an empty queue ends this
    bootstrap worker. This is not a scheduler for future dependent pipeline steps.
    Console output can repeat if the process dies before completion is committed.
    """
    with open_queue(state_directory) as queue:
        while os.getppid() == coordinator_pid:
            task = claim_task(
                queue,
                step=PRINT_TASK_STEP,
                processing_version=BOOTSTRAP_PROCESSING_VERSION,
            )
            if task is None:
                return

            summary = TaskSummary(
                task_id=task.task_id,
                step=task.step,
                attempt_count=task.attempt_count,
                worker_pid=os.getpid(),
            )
            print(summary.model_dump_json(), flush=True)
            complete_task(queue, task)
