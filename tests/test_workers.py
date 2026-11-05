import os
import sqlite3
from pathlib import Path

import pytest

from redactor.persistence.files import register_file
from redactor.persistence.queue import get_task
from redactor.schemas.worker import TaskSummary
from redactor.utils.constants import (
    BOOTSTRAP_PROCESSING_VERSION,
    PRINT_TASK_STEP,
    STATE_DIRECTORY,
    STATUS_PENDING,
    STATUS_RUNNING,
    STATUS_SUCCEEDED,
)
from redactor.workers.run import consume_tasks


def test_worker_prints_only_safe_metadata_and_acknowledges_its_own_step(
    connection: sqlite3.Connection,
    source_file: Path,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    clinical = register_file(connection, source_file, "redact", "v1")
    obsolete = register_file(connection, source_file, PRINT_TASK_STEP, "old-version")
    diagnostic = register_file(
        connection, source_file, PRINT_TASK_STEP, BOOTSTRAP_PROCESSING_VERSION
    )

    consume_tasks(tmp_path / STATE_DIRECTORY, os.getppid())
    output = capsys.readouterr().out
    summary = TaskSummary.model_validate_json(output)
    assert summary.task_id == diagnostic.task_id
    assert summary.attempt_count == 1
    assert summary.worker_pid == os.getpid()
    assert source_file.name not in output
    assert source_file.read_text() not in output
    assert get_task(connection, diagnostic.task_id).status == STATUS_SUCCEEDED
    assert get_task(connection, clinical.task_id).status == STATUS_PENDING
    assert get_task(connection, obsolete.task_id).status == STATUS_PENDING

    consume_tasks(tmp_path / STATE_DIRECTORY, os.getppid())
    assert capsys.readouterr().out == ""
    assert get_task(connection, diagnostic.task_id).attempt_count == 1


def test_worker_stops_claiming_when_its_parent_is_gone(
    connection: sqlite3.Connection, source_file: Path, tmp_path: Path
) -> None:
    task = register_file(
        connection, source_file, PRINT_TASK_STEP, BOOTSTRAP_PROCESSING_VERSION
    )
    consume_tasks(tmp_path / STATE_DIRECTORY, os.getpid())
    assert get_task(connection, task.task_id).status == STATUS_PENDING


def test_output_failure_does_not_acknowledge_the_task(
    connection: sqlite3.Connection,
    source_file: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    task = register_file(
        connection, source_file, PRINT_TASK_STEP, BOOTSTRAP_PROCESSING_VERSION
    )

    def fail_print(message: str, *, flush: bool) -> None:
        raise BrokenPipeError("closed output")

    monkeypatch.setattr("builtins.print", fail_print)
    with pytest.raises(BrokenPipeError):
        consume_tasks(tmp_path / STATE_DIRECTORY, os.getppid())
    assert get_task(connection, task.task_id).status == STATUS_RUNNING
