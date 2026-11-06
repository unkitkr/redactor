import subprocess
import sys
from contextlib import closing
from pathlib import Path

import pytest

from redactor.coordinator.ownership import own_run
from redactor.persistence.database import open_database
from redactor.persistence.files.registration import register_file
from redactor.persistence.queue.tasks import (
    claim_task,
    get_task,
    iter_attempts,
    iter_tasks,
)
from redactor.schemas.worker import TaskSummary
from redactor.utils.constants import (
    BOOTSTRAP_PROCESSING_VERSION,
    OUTPUT_DIRECTORY,
    PRINT_TASK_STEP,
    STATE_DIRECTORY,
    STATUS_INTERRUPTED,
    STATUS_RUNNING,
    STATUS_SUCCEEDED,
)
from redactor.utils.errors import (
    ERROR_INPUT_DIRECTORY,
    ERROR_INPUT_ENTRY,
    ERROR_RUN_ACTIVE,
)


def invoke_coordinator(inputs: Path, state: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "redactor",
            "--diagnostic",
            "--input",
            str(inputs),
            "--state",
            str(state),
            "--workers",
            "2",
        ],
        capture_output=True,
        text=True,
        timeout=15,
    )


def test_coordinator_processes_inventory_once_across_restarts(tmp_path: Path) -> None:
    inputs = tmp_path / "input"
    inputs.mkdir()
    for index in range(20):
        (inputs / f"sensitive-filename-{index}.txt").write_text("sensitive contents")
    state = tmp_path / STATE_DIRECTORY

    first = invoke_coordinator(inputs, state)
    assert first.returncode == 0, first.stderr
    summaries = [
        TaskSummary.model_validate_json(line) for line in first.stdout.splitlines()
    ]
    assert len(summaries) == 20
    assert len({summary.task_id for summary in summaries}) == 20
    assert all(summary.attempt_count == 1 for summary in summaries)
    assert "sensitive" not in first.stdout + first.stderr

    second = invoke_coordinator(inputs, state)
    assert second.returncode == 0, second.stderr
    assert second.stdout == ""
    with closing(open_database(state)) as connection:
        tasks = list(iter_tasks(connection))
        assert len(tasks) == 20
        assert all(task.status == STATUS_SUCCEEDED for task in tasks)
        assert all(task.attempt_count == 1 for task in tasks)
    assert not (tmp_path / OUTPUT_DIRECTORY).exists()
    assert all(path.read_text() == "sensitive contents" for path in inputs.iterdir())


def test_startup_recovers_an_interrupted_attempt(tmp_path: Path) -> None:
    inputs = tmp_path / "input"
    inputs.mkdir()
    source = inputs / "records.csv"
    source.write_bytes(b"row\n")
    state = tmp_path / STATE_DIRECTORY
    with closing(open_database(state)) as connection:
        task = register_file(
            connection, source, PRINT_TASK_STEP, BOOTSTRAP_PROCESSING_VERSION
        )
        assert claim_task(connection) is not None

    result = invoke_coordinator(inputs, state)
    assert result.returncode == 0, result.stderr
    summary = TaskSummary.model_validate_json(result.stdout)
    assert summary.attempt_count == 2
    with closing(open_database(state)) as connection:
        assert get_task(connection, task.task_id).status == STATUS_SUCCEEDED
        attempts = list(iter_attempts(connection, task.task_id))
        assert [attempt.status for attempt in attempts] == [
            STATUS_INTERRUPTED,
            STATUS_SUCCEEDED,
        ]


def test_second_coordinator_cannot_reset_running_work(tmp_path: Path) -> None:
    inputs = tmp_path / "input"
    inputs.mkdir()
    source = inputs / "records.csv"
    source.write_bytes(b"row\n")
    state = tmp_path / STATE_DIRECTORY
    with own_run(state), closing(open_database(state)) as connection:
        task = register_file(
            connection, source, PRINT_TASK_STEP, BOOTSTRAP_PROCESSING_VERSION
        )
        assert claim_task(connection) is not None
        result = invoke_coordinator(inputs, state)
        assert result.returncode != 0
        assert result.stderr.strip() == ERROR_RUN_ACTIVE
        assert get_task(connection, task.task_id).status == STATUS_RUNNING


def test_empty_inventory_exits_successfully(tmp_path: Path) -> None:
    inputs = tmp_path / "input"
    inputs.mkdir()
    result = invoke_coordinator(inputs, tmp_path / STATE_DIRECTORY)
    assert result.returncode == 0, result.stderr
    assert result.stdout == ""


def test_invalid_input_fails_before_initializing_state(tmp_path: Path) -> None:
    state = tmp_path / STATE_DIRECTORY
    result = invoke_coordinator(tmp_path / "missing", state)
    assert result.returncode != 0
    assert result.stderr.strip() == ERROR_INPUT_DIRECTORY
    assert not state.exists()


def test_incomplete_inventory_does_not_start_workers(tmp_path: Path) -> None:
    inputs = tmp_path / "input"
    inputs.mkdir()
    source = inputs / "ordinary-file"
    source.write_bytes(b"row\n")
    (inputs / "alias").symlink_to(source)
    state = tmp_path / STATE_DIRECTORY
    result = invoke_coordinator(inputs, state)
    assert result.returncode != 0
    assert result.stderr.strip() == ERROR_INPUT_ENTRY
    assert result.stdout == ""
    with closing(open_database(state)) as connection:
        assert all(task.attempt_count == 0 for task in iter_tasks(connection))


@pytest.mark.parametrize("worker_count", [0, -1])
def test_worker_count_must_be_positive(tmp_path: Path, worker_count: int) -> None:
    from pydantic import ValidationError

    from redactor.schemas.coordinator import CoordinatorConfig

    with pytest.raises(ValidationError):
        CoordinatorConfig(
            input_directory=tmp_path,
            state_directory=tmp_path / STATE_DIRECTORY,
            worker_count=worker_count,
        )
