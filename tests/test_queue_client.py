import sqlite3
from pathlib import Path

import pytest

from redactor.persistence.client import open_queue
from redactor.persistence.files import register_file
from redactor.persistence.queue import get_task
from redactor.utils.constants import STATE_DIRECTORY, STATUS_RUNNING


def test_client_closes_connection_without_acknowledging_unfinished_work(
    connection: sqlite3.Connection, source_file: Path, tmp_path: Path
) -> None:
    task = register_file(connection, source_file, "inspect", "v1")
    with pytest.raises(ValueError, match="work interrupted"):
        with open_queue(
            tmp_path / STATE_DIRECTORY, step="inspect", processing_version="v1"
        ) as queue:
            assert queue.claim() is not None
            raise ValueError("work interrupted")

    assert get_task(connection, task.task_id).status == STATUS_RUNNING
    with pytest.raises(sqlite3.ProgrammingError, match="closed database"):
        queue.claim()
