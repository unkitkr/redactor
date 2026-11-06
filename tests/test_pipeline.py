"""Integration coverage for idle workers, durable transitions and blocked graphs."""

import select
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

from redactor.persistence.database import state_directory
from redactor.persistence.files.registration import prepare_successor, register_file
from redactor.persistence.queue.scheduling import work_remains
from redactor.persistence.queue.tasks import (
    claim_task,
    complete_task,
    enqueue_task,
    fail_task,
    get_task,
    iter_tasks,
)
from redactor.schemas.persistence import Task
from redactor.schemas.pipeline import StepResult
from redactor.utils.constants import STATUS_RUNNING, STATUS_SUCCEEDED
from redactor.utils.errors import (
    ERROR_PIPELINE_BLOCKED,
    ERROR_PROCESSING,
    ERROR_UNKNOWN_STEP,
)
from redactor.workers.pipeline import execute_task


def test_worker_waits_for_other_worker_then_drains_durable_successors(
    connection: sqlite3.Connection, source_file: Path
) -> None:
    registered = register_file(
        connection, source_file, "inspect", "pipeline-integration-v1"
    )
    claimed = claim_task(connection, steps=("inspect",))
    assert claimed is not None
    assert claim_task(connection, steps=()) is None

    command = [
        sys.executable,
        str(Path(__file__).parent / "support" / "consume_pipeline.py"),
        str(state_directory(connection)),
    ]
    with subprocess.Popen(
        command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
    ) as worker:
        try:
            assert worker.stdout is not None
            assert select.select([worker.stdout], [], [], 5)[0]
            assert worker.stdout.readline() == "ready\n"
            # This worker cannot claim inspection. It must await the running owner.
            with pytest.raises(subprocess.TimeoutExpired):
                worker.wait(timeout=0.15)
            complete_task(
                connection,
                claimed,
                successors=(prepare_successor(connection, claimed, "analyze"),),
            )
            stdout, stderr = worker.communicate(timeout=5)
            assert worker.returncode == 0, stderr
            assert stdout == ""
        finally:
            if worker.poll() is None:
                worker.kill()
                worker.communicate(timeout=5)

    tasks = list(iter_tasks(connection))
    assert {task.step for task in tasks} == {"inspect", "analyze", "rewrite"}
    assert all(task.status == STATUS_SUCCEEDED for task in tasks)
    assert all(task.attempt_count == 1 for task in tasks)
    assert all(task.input_sha256 == registered.input_sha256 for task in tasks)

    replay = subprocess.run(command, capture_output=True, timeout=5, check=False)
    assert replay.returncode == 0, replay.stderr
    assert list(iter_tasks(connection)) == tasks


def test_failed_prerequisite_and_unknown_step_cannot_look_complete(
    connection: sqlite3.Connection, source_file: Path
) -> None:
    root = register_file(connection, source_file, "inspect", "pipeline-integration-v1")
    enqueue_task(
        connection,
        prepare_successor(connection, root, "analyze"),
        dependencies=(root.task_id,),
    )
    claimed = claim_task(connection, steps=("inspect",))
    assert claimed is not None
    with pytest.raises(ValueError, match=ERROR_UNKNOWN_STEP):
        execute_task(connection, claimed, {})
    assert get_task(connection, claimed.task_id).status == STATUS_RUNNING

    def broken_step(database: sqlite3.Connection, task: Task) -> StepResult:
        raise RuntimeError(ERROR_PROCESSING)

    with pytest.raises(RuntimeError, match=ERROR_PROCESSING):
        execute_task(connection, claimed, {"inspect": broken_step})
    assert get_task(connection, claimed.task_id).status == STATUS_RUNNING
    fail_task(connection, claimed, ERROR_PROCESSING)
    with pytest.raises(RuntimeError, match=ERROR_PIPELINE_BLOCKED):
        work_remains(connection, root.processing_version, ("inspect", "analyze"))
