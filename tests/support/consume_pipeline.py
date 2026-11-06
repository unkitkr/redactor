"""Exercise an idle worker and real durable successors in a fresh interpreter."""

import os
import sqlite3
import sys
from pathlib import Path

from redactor.persistence.files.registration import prepare_successor
from redactor.schemas.persistence import Task
from redactor.schemas.pipeline import StepResult
from redactor.workers.run import consume_tasks


def advance(connection: sqlite3.Connection, task: Task) -> StepResult:
    if task.step == "analyze":
        return StepResult(successors=(prepare_successor(connection, task, "rewrite"),))
    return StepResult()


if __name__ == "__main__":
    print("ready", flush=True)
    consume_tasks(
        Path(sys.argv[1]),
        os.getppid(),
        processing_version="pipeline-integration-v1",
        handlers={"inspect": advance, "analyze": advance, "rewrite": advance},
        eligible_steps=("analyze", "rewrite"),
    )
