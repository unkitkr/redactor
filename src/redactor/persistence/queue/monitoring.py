"""Observe committed queue state without migrations, recovery, or file reads."""

import re
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from time import monotonic

from redactor.schemas.monitoring import (
    QueueSnapshot,
    RunSummary,
    StepCounts,
    TaskProgress,
)
from redactor.utils.constants import (
    DATABASE_FILENAME,
    MONITOR_BUSY,
    MONITOR_MAX_RUNS,
    MONITOR_MAX_STEP_GROUPS,
    MONITOR_MAX_TASKS,
    MONITOR_MISSING,
    MONITOR_PROGRESS_INSTRUCTIONS,
    MONITOR_QUERY_SECONDS,
    MONITOR_READY,
    MONITOR_RUN_ID_PATTERN,
    MONITOR_SQLITE_ERROR_MASK,
    MONITOR_SQLITE_TIMEOUT_SECONDS,
    MONITOR_STEPS,
    MONITOR_TASK_STATUSES,
    MONITOR_UNAVAILABLE,
    STATUS_RUNNING,
    STEP_ANALYZE,
    STEP_PUBLISH,
    STEP_QUARANTINE,
    STEP_RESOLVE,
    STEP_REWRITE,
)
from redactor.utils.errors import (
    ERROR_MONITOR_BUSY,
    ERROR_MONITOR_MISSING,
    ERROR_MONITOR_RUN_MISSING,
    ERROR_MONITOR_UNAVAILABLE,
    FAILURE_CODES,
)


def read_queue_snapshot(
    state_directory: Path, processing_version: str | None = None
) -> QueueSnapshot:
    """Return a short read transaction; callers never receive an open connection."""
    observed_at = datetime.now(UTC)
    connection = None
    try:
        if processing_version is not None and not re.fullmatch(
            MONITOR_RUN_ID_PATTERN, processing_version
        ):
            return QueueSnapshot(
                status=MONITOR_MISSING,
                reason_code=ERROR_MONITOR_RUN_MISSING,
                observed_at=observed_at,
            )
        database = state_directory.resolve() / DATABASE_FILENAME
        if not database.is_file():
            return QueueSnapshot(
                status=MONITOR_MISSING,
                reason_code=ERROR_MONITOR_MISSING,
                observed_at=observed_at,
            )
        deadline = monotonic() + MONITOR_QUERY_SECONDS
        connection = sqlite3.connect(
            database.as_uri() + "?mode=ro",
            uri=True,
            timeout=MONITOR_SQLITE_TIMEOUT_SECONDS,
            isolation_level=None,
        )
        connection.row_factory = sqlite3.Row
        connection.set_progress_handler(
            lambda: int(monotonic() >= deadline), MONITOR_PROGRESS_INSTRUCTIONS
        )
        connection.execute("PRAGMA query_only = ON")
        connection.execute("PRAGMA trusted_schema = OFF")
        connection.execute("BEGIN")
        return _read_snapshot(connection, processing_version, observed_at)
    except sqlite3.Error as error:
        code = getattr(error, "sqlite_errorcode", 0) & MONITOR_SQLITE_ERROR_MASK
        busy = code in (
            sqlite3.SQLITE_BUSY,
            sqlite3.SQLITE_LOCKED,
            sqlite3.SQLITE_INTERRUPT,
        )
        return QueueSnapshot(
            status=MONITOR_BUSY if busy else MONITOR_UNAVAILABLE,
            reason_code=ERROR_MONITOR_BUSY if busy else ERROR_MONITOR_UNAVAILABLE,
            observed_at=observed_at,
        )
    except (OSError, ValueError):
        return QueueSnapshot(
            status=MONITOR_UNAVAILABLE,
            reason_code=ERROR_MONITOR_UNAVAILABLE,
            observed_at=observed_at,
        )
    finally:
        if connection is not None:
            connection.close()


def _read_snapshot(
    connection: sqlite3.Connection,
    requested_version: str | None,
    observed_at: datetime,
) -> QueueSnapshot:
    rows = connection.execute(
        """
        SELECT processing_version, MIN(created_at) AS created_at,
            MAX(updated_at) AS updated_at, COUNT(*) AS task_count
        FROM tasks GROUP BY processing_version
        ORDER BY COALESCE(MAX(CASE WHEN step = ? THEN created_at END),
            MAX(created_at)) DESC, processing_version
        LIMIT ?
        """,
        (STEP_RESOLVE, MONITOR_MAX_RUNS),
    ).fetchall()
    runs = tuple(RunSummary.model_validate(dict(row)) for row in rows)
    selected = requested_version or (runs[0].processing_version if runs else None)
    if selected is None:
        return QueueSnapshot(status=MONITOR_READY, observed_at=observed_at, runs=runs)
    groups = connection.execute(
        """
        SELECT step, status, COUNT(*) AS total FROM tasks
        WHERE processing_version = ? GROUP BY step, status LIMIT ?
        """,
        (selected, MONITOR_MAX_STEP_GROUPS + 1),
    ).fetchall()
    if not groups:
        return QueueSnapshot(
            status=MONITOR_MISSING,
            reason_code=ERROR_MONITOR_RUN_MISSING,
            observed_at=observed_at,
            processing_version=selected,
            runs=runs,
        )
    counts = {step: dict.fromkeys(MONITOR_TASK_STATUSES, 0) for step in MONITOR_STEPS}
    for row in groups:
        if row["step"] not in counts or row["status"] not in MONITOR_TASK_STATUSES:
            raise ValueError(ERROR_MONITOR_UNAVAILABLE)
        counts[row["step"]][row["status"]] = row["total"]
    steps = tuple(
        StepCounts.model_validate(
            {"step": step, **values, "total": sum(values.values())}
        )
        for step, values in counts.items()
    )
    return QueueSnapshot(
        status=MONITOR_READY,
        observed_at=observed_at,
        processing_version=selected,
        runs=runs,
        steps=steps,
        tasks=_read_tasks(connection, selected),
        task_count=sum(item.total for item in steps),
        published_files=next(
            item.succeeded for item in steps if item.step == STEP_PUBLISH
        ),
        quarantined_files=next(
            item.succeeded for item in steps if item.step == STEP_QUARANTINE
        ),
        resolve_tasks=next(item.total for item in steps if item.step == STEP_RESOLVE),
    )


def _read_tasks(
    connection: sqlite3.Connection, processing_version: str
) -> tuple[TaskProgress, ...]:
    rows = connection.execute(
        """
        SELECT task_id, step, status, attempt_count, updated_at, failure_code
        FROM tasks WHERE processing_version = ?
        ORDER BY (status = ?) DESC, updated_at DESC, task_id LIMIT ?
        """,
        (processing_version, STATUS_RUNNING, MONITOR_MAX_TASKS),
    ).fetchall()
    tables = {
        row[0]
        for row in connection.execute(
            """
            SELECT name FROM sqlite_schema WHERE type = 'table'
                AND name IN ('identity_scan_progress', 'checkpoints')
            """
        )
    }
    tasks = []
    for row in rows:
        values = dict(row)
        if values["failure_code"] not in FAILURE_CODES:
            values["failure_code"] = None
        task = TaskProgress.model_validate(values)
        checkpoint = None
        if task.step == STEP_ANALYZE and "identity_scan_progress" in tables:
            checkpoint = connection.execute(
                """
                SELECT record_count, input_offset FROM identity_scan_progress
                WHERE task_id = ?
                """,
                (task.task_id,),
            ).fetchone()
        elif task.step == STEP_REWRITE and "checkpoints" in tables:
            checkpoint = connection.execute(
                """
                SELECT record_count, input_offset FROM checkpoints
                WHERE task_id = ? ORDER BY sequence DESC LIMIT 1
                """,
                (task.task_id,),
            ).fetchone()
        if checkpoint is not None:
            task = TaskProgress.model_validate(
                {
                    **values,
                    "checkpoint_records": checkpoint["record_count"],
                    "input_offset": checkpoint["input_offset"],
                }
            )
        tasks.append(task)
    return tuple(tasks)
