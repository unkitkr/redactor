"""Read-only queue snapshots remain bounded and observe committed WAL state."""

import hashlib
import sqlite3
from contextlib import closing
from datetime import UTC, datetime, timedelta
from pathlib import Path
from time import monotonic

import pytest

from redactor.persistence.database import open_database
from redactor.persistence.queue import monitoring
from redactor.persistence.queue.tasks import enqueue_task
from redactor.schemas.persistence import TaskSpec
from redactor.utils.constants import (
    BOOTSTRAP_PROCESSING_VERSION,
    DATABASE_FILENAME,
    MONITOR_MAX_RUNS,
    MONITOR_MAX_TASKS,
)
from redactor.utils.errors import (
    ERROR_MONITOR_BUSY,
    ERROR_MONITOR_MISSING,
    ERROR_MONITOR_RUN_MISSING,
    ERROR_MONITOR_UNAVAILABLE,
    ERROR_PROCESSING,
)


def insert_task(
    connection: sqlite3.Connection,
    label: str,
    version: str,
    step: str,
    status: str = "pending",
    timestamp: str = "2026-01-01T00:00:00+00:00",
    failure_code: str | None = None,
) -> str:
    task_id = hashlib.sha256(label.encode()).hexdigest()
    enqueue_task(
        connection,
        TaskSpec(
            task_id=task_id,
            input_path=Path("/private/Patient Alice Stone/123456.csv"),
            input_sha256="f" * 64,
            input_size=1000,
            step=step,
            processing_version=version,
            temporary_directory=Path("/private/secret-artifacts"),
        ),
    )
    connection.execute(
        """
        UPDATE tasks SET status = ?, created_at = ?, updated_at = ?,
            attempt_count = 2, failure_code = ?, result_path = ? WHERE task_id = ?
        """,
        (status, timestamp, timestamp, failure_code, "/private/secret-result", task_id),
    )
    return task_id


def test_wal_snapshot_separates_runs_and_keeps_checkpoint_metadata_private(
    tmp_path: Path,
) -> None:
    state = tmp_path / "state"
    old, current = "a" * 64, "b" * 64
    with closing(open_database(state)) as connection:
        assert connection.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
        insert_task(connection, "old-resolve", old, "resolve", "succeeded")
        insert_task(
            connection,
            "current-resolve",
            current,
            "resolve",
            "succeeded",
            "2026-01-05T00:00:00+00:00",
        )
        # New work in an older run does not make it the newest frozen run.
        insert_task(
            connection,
            "old-new-task",
            old,
            "rewrite",
            "succeeded",
            "2026-01-09T00:00:00+00:00",
        )
        analysis = insert_task(connection, "analysis", current, "analyze", "running")
        rewrite = insert_task(connection, "rewrite", current, "rewrite", "running")
        published = insert_task(
            connection, "published", current, "publish", "succeeded"
        )
        insert_task(connection, "not-published", current, "publish")
        insert_task(connection, "quarantine", current, "quarantine", "succeeded")
        insert_task(connection, "not-quarantined", current, "quarantine", "failed")
        failed = insert_task(
            connection,
            "safe-failure",
            current,
            "verify",
            "failed",
            timestamp="2026-01-04T00:00:00+00:00",
            failure_code=ERROR_PROCESSING,
        )
        unsafe = insert_task(
            connection,
            "unsafe-failure",
            current,
            "verify",
            "failed",
            timestamp="2026-01-04T00:00:00+00:00",
            failure_code="Patient Alice Stone 123456",
        )
        connection.execute(
            """
            INSERT INTO identity_scan_progress (
                task_id, sequence, input_offset, record_count, batch_digest
            ) VALUES (?, 1, 128, 10, ?)
            """,
            (analysis, "secret-batch-digest"),
        )
        for sequence in (1, 2):
            connection.execute(
                """
                INSERT INTO checkpoints (
                    task_id, sequence, artifact_path, input_offset, output_offset,
                    record_count, output_prefix_sha256, counts_json, cursor_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    rewrite,
                    sequence,
                    "/private/Alice.part",
                    sequence * 128,
                    10,
                    sequence * 10,
                    "f" * 64,
                    '{"Patient Alice":123456}',
                    '{"private_cursor":"123456"}',
                ),
            )
        for number in range(60):
            insert_task(connection, f"queued-{number}", current, "inspect")
        before = tuple(tuple(row) for row in connection.execute("SELECT * FROM tasks"))
        version = connection.execute("PRAGMA user_version").fetchone()[0]
        connection.execute("BEGIN IMMEDIATE")
        connection.execute(
            "UPDATE tasks SET status = 'failed' WHERE task_id = ?", (published,)
        )
        snapshot = monitoring.read_queue_snapshot(state)
        connection.rollback()
        assert snapshot.status == "ready"
        assert snapshot.processing_version == current
        assert snapshot.task_count == 69
        assert snapshot.published_files == snapshot.quarantined_files == 1
        assert snapshot.resolve_tasks == 1
        assert len(snapshot.tasks) == MONITOR_MAX_TASKS
        assert all(task.status == "running" for task in snapshot.tasks[:2])
        progress = {task.task_id: task for task in snapshot.tasks}
        assert progress[analysis].checkpoint_records == 10
        assert progress[analysis].input_offset == 128
        assert progress[rewrite].checkpoint_records == 20
        assert progress[rewrite].input_offset == 256
        # Inspect all safe failure values independently of the bounded recent list.
        failures = monitoring.read_queue_snapshot(state, current).model_dump_json()
        assert "Patient" not in failures and "123456" not in failures
        assert "/private" not in failures and "secret" not in failures
        assert progress[failed].failure_code == ERROR_PROCESSING
        assert progress[unsafe].failure_code is None
        assert (
            tuple(tuple(row) for row in connection.execute("SELECT * FROM tasks"))
            == before
        )
        assert connection.execute("PRAGMA user_version").fetchone()[0] == version
        old_snapshot = monitoring.read_queue_snapshot(state, old)
        assert old_snapshot.task_count == 2
        assert old_snapshot.published_files == old_snapshot.quarantined_files == 0
        assert connection.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()[0] == 0


def test_snapshot_bounds_run_history_and_interrupts_expensive_reads(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    state = tmp_path / "state"
    with closing(open_database(state)) as connection:
        first_version = ""
        for number in range(35):
            version = hashlib.sha256(f"run-{number}".encode()).hexdigest()
            first_version = first_version or version
            created = datetime(2026, 1, 1, tzinfo=UTC) + timedelta(minutes=number)
            insert_task(
                connection,
                f"task-{number}",
                version,
                "resolve",
                timestamp=created.isoformat(),
            )
        insert_task(
            connection,
            "bootstrap",
            BOOTSTRAP_PROCESSING_VERSION,
            "print_task",
            timestamp="2026-01-02T00:00:00+00:00",
        )
        snapshot = monitoring.read_queue_snapshot(state)
        assert snapshot.status == "ready"
        assert snapshot.processing_version == BOOTSTRAP_PROCESSING_VERSION
        assert len(snapshot.runs) == MONITOR_MAX_RUNS
        assert len(snapshot.model_dump_json()) < 20000
        older = monitoring.read_queue_snapshot(state, first_version)
        assert older.status == "ready" and older.task_count == 1
        assert all(run.processing_version != first_version for run in older.runs)
        assert (
            monitoring.read_queue_snapshot(state, "f" * 64).reason_code
            == ERROR_MONITOR_RUN_MISSING
        )
        invalid = monitoring.read_queue_snapshot(state, "Patient Alice Stone")
        assert invalid.reason_code == ERROR_MONITOR_RUN_MISSING
        assert "Patient" not in invalid.model_dump_json()
        with monkeypatch.context() as patch:
            patch.setattr(monitoring, "MONITOR_QUERY_SECONDS", 0)
            patch.setattr(monitoring, "MONITOR_PROGRESS_INSTRUCTIONS", 1)
            started = monotonic()
            busy = monitoring.read_queue_snapshot(state)
            assert busy.status == "busy" and busy.reason_code == ERROR_MONITOR_BUSY
            assert monotonic() - started < 0.5
        assert monitoring.read_queue_snapshot(state).status == "ready"
        assert connection.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()[0] == 0


def test_missing_corrupt_and_locked_state_never_creates_or_repairs_database(
    tmp_path: Path,
) -> None:
    missing = tmp_path / "missing"
    snapshot = monitoring.read_queue_snapshot(missing)
    assert (
        snapshot.status == "missing" and snapshot.reason_code == ERROR_MONITOR_MISSING
    )
    assert not missing.exists()
    broken = tmp_path / "broken"
    broken.mkdir()
    database = broken / DATABASE_FILENAME
    database.write_bytes(b"raw identifying data must not become an error message")
    before = database.read_bytes()
    unavailable = monitoring.read_queue_snapshot(broken)
    assert unavailable.status == "unavailable"
    assert unavailable.reason_code == ERROR_MONITOR_UNAVAILABLE
    assert "identifying" not in unavailable.model_dump_json()
    assert database.read_bytes() == before
    empty = tmp_path / "empty"
    empty.mkdir()
    with closing(sqlite3.connect(empty / DATABASE_FILENAME)) as connection:
        assert monitoring.read_queue_snapshot(empty).status == "unavailable"
        assert connection.execute("SELECT name FROM sqlite_schema").fetchall() == []
        connection.execute("BEGIN EXCLUSIVE")
        started = monotonic()
        locked = monitoring.read_queue_snapshot(empty)
        assert locked.status == "busy" and locked.reason_code == ERROR_MONITOR_BUSY
        assert monotonic() - started < 0.5
        connection.rollback()
