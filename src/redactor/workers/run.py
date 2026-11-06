"""Claim durable tasks and pass them to the pipeline until the run settles."""

import os
import time
from collections.abc import Mapping, Sequence
from pathlib import Path

from redactor.persistence.client import claim_task, open_queue
from redactor.persistence.scheduling import work_remains
from redactor.schemas.pipeline import StepHandler
from redactor.utils.constants import (
    BOOTSTRAP_PROCESSING_VERSION,
    PRINT_TASK_STEP,
    WORKER_POLL_SECONDS,
)
from redactor.workers.diagnostic import print_task
from redactor.workers.pipeline import execute_task


def consume_tasks(
    state_directory: Path,
    coordinator_pid: int,
    *,
    processing_version: str = BOOTSTRAP_PROCESSING_VERSION,
    handlers: Mapping[str, StepHandler] | None = None,
    eligible_steps: Sequence[str] | None = None,
) -> None:
    handlers = {PRINT_TASK_STEP: print_task} if handlers is None else handlers
    eligible_steps = tuple(handlers) if eligible_steps is None else eligible_steps
    with open_queue(state_directory) as queue:
        while os.getppid() == coordinator_pid:
            task = claim_task(
                queue,
                steps=eligible_steps,
                processing_version=processing_version,
            )
            if task is None:
                if not work_remains(queue, processing_version, handlers.keys()):
                    return
                time.sleep(WORKER_POLL_SECONDS)
                continue
            execute_task(queue, task, handlers)
