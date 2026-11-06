"""Exercise real worker failures and idle readers against native SQLite state."""

import os
import sqlite3
import subprocess
import sys
from contextlib import closing
from pathlib import Path

from redactor.coordinator.ownership import own_run
from redactor.persistence.database import open_database, transaction
from redactor.persistence.files.registration import register_file
from redactor.persistence.queue.tasks import claim_task, get_task
from redactor.schemas.diagnostics import FailureDiagnostic
from redactor.utils.constants import DATABASE_FILENAME, STATE_DIRECTORY, STATUS_RUNNING


def test_worker_records_safe_sqlite_failure_without_exposing_database_bytes(
    tmp_path: Path,
) -> None:
    state = tmp_path / STATE_DIRECTORY
    with own_run(state) as descriptor:
        (state / DATABASE_FILENAME).write_bytes(
            b"private patient data, broken database"
        )
        process = subprocess.run(
            [
                sys.executable,
                "-m",
                "redactor.workers",
                str(state),
                str(os.getpid()),
                str(descriptor),
            ],
            pass_fds=(descriptor,),
            capture_output=True,
            text=True,
            timeout=15,
        )
    assert process.returncode == 1
    assert process.stdout == ""
    diagnostic = FailureDiagnostic.model_validate_json(process.stderr)
    assert diagnostic.category == "sqlite"
    assert diagnostic.sqlite_error_code == sqlite3.SQLITE_NOTADB
    records = list(state.glob("worker-failure-*.json"))
    assert len(records) == 1
    assert FailureDiagnostic.model_validate_json(records[0].read_bytes()) == diagnostic
    assert "private" not in process.stderr
    assert str(tmp_path) not in process.stderr


def test_idle_worker_does_not_request_a_write_lock(tmp_path: Path) -> None:
    source = tmp_path / "source.txt"
    source.write_text("synthetic record")
    with (
        closing(open_database(tmp_path / STATE_DIRECTORY)) as writer,
        closing(open_database(tmp_path / STATE_DIRECTORY)) as reader,
    ):
        registered = register_file(writer, source, "analyze", "diagnostic-v1")
        reader.execute("PRAGMA busy_timeout = 1")
        with transaction(writer):
            assert claim_task(reader, steps=("publish",)) is None
        claimed = claim_task(reader, steps=("analyze",))
        assert claimed is not None
        with transaction(writer):
            assert claim_task(reader) is None
        assert get_task(writer, registered.task_id).status == STATUS_RUNNING
        assert get_task(writer, registered.task_id).attempt_count == 1
