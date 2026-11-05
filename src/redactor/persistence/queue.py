"""Durable task transitions; callers own the connection and coordinator lock."""

import sqlite3
from collections.abc import Iterator, Sequence
from datetime import UTC, datetime
from uuid import uuid4

from redactor.persistence.database import transaction
from redactor.schemas.persistence import Artifact, Attempt, Task, TaskSpec
from redactor.utils.constants import (
    ERROR_COMPLETION_CHANGED,
    ERROR_DEPENDENCIES_CHANGED,
    ERROR_INTERRUPTED,
    ERROR_INVALID_FAILURE_CODE,
    ERROR_INVALID_TRANSITION,
    ERROR_STALE_ATTEMPT,
    ERROR_TASK_ID_CONFLICT,
    ERROR_TASK_NOT_FOUND,
    ERROR_UNKNOWN_DEPENDENCY,
    FAILURE_CODES,
    FILE_LOCATION_FIELDS,
    STATUS_FAILED,
    STATUS_INTERRUPTED,
    STATUS_PENDING,
    STATUS_RUNNING,
    STATUS_SUCCEEDED,
)


def enqueue_task(
    connection: sqlite3.Connection,
    spec: TaskSpec,
    *,
    dependencies: Sequence[str] = (),
) -> Task:
    """Insert once; dependencies must exist and cannot change on rediscovery."""
    with transaction(connection):
        _insert_task(connection, spec, dependencies)
    return get_task(connection, spec.task_id)


def _insert_task(
    connection: sqlite3.Connection, spec: TaskSpec, dependencies: Sequence[str]
) -> None:
    required = set(dependencies)
    existing = connection.execute(
        "SELECT * FROM tasks WHERE task_id = ?", (spec.task_id,)
    ).fetchone()
    if existing is not None:
        stored_task = Task.model_validate(dict(existing))
        for field in TaskSpec.model_fields:
            stored_value = getattr(stored_task, field)
            incoming_value = getattr(spec, field)
            if field in FILE_LOCATION_FIELDS and (
                stored_value is None or incoming_value is None
            ):
                continue
            if stored_value != incoming_value:
                raise ValueError(ERROR_TASK_ID_CONFLICT)
        stored = {
            row[0]
            for row in connection.execute(
                "SELECT depends_on FROM dependencies WHERE task_id = ?", (spec.task_id,)
            )
        }
        if stored != required:
            raise ValueError(ERROR_DEPENDENCIES_CHANGED)
        connection.execute(
            """
            UPDATE tasks SET
                temporary_directory = COALESCE(temporary_directory, ?),
                output_path = COALESCE(output_path, ?)
            WHERE task_id = ?
            """,
            (
                str(spec.temporary_directory) if spec.temporary_directory else None,
                str(spec.output_path) if spec.output_path else None,
                spec.task_id,
            ),
        )
        return

    for dependency in required:
        if (
            connection.execute(
                "SELECT task_id FROM tasks WHERE task_id = ?", (dependency,)
            ).fetchone()
            is None
        ):
            raise ValueError(ERROR_UNKNOWN_DEPENDENCY)

    now = datetime.now(UTC).isoformat()
    connection.execute(
        """
        INSERT INTO tasks (
            task_id, input_path, input_sha256, input_size, step,
            processing_version, temporary_directory, output_path,
            status, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            spec.task_id,
            str(spec.input_path),
            spec.input_sha256,
            spec.input_size,
            spec.step,
            spec.processing_version,
            str(spec.temporary_directory) if spec.temporary_directory else None,
            str(spec.output_path) if spec.output_path else None,
            STATUS_PENDING,
            now,
            now,
        ),
    )
    connection.executemany(
        "INSERT INTO dependencies (task_id, depends_on) VALUES (?, ?)",
        ((spec.task_id, dependency) for dependency in sorted(required)),
    )


def get_task(connection: sqlite3.Connection, task_id: str) -> Task:
    row = connection.execute(
        "SELECT * FROM tasks WHERE task_id = ?", (task_id,)
    ).fetchone()
    if row is None:
        raise KeyError(ERROR_TASK_NOT_FOUND)
    return Task.model_validate(dict(row))


def iter_tasks(connection: sqlite3.Connection) -> Iterator[Task]:
    cursor = connection.execute("SELECT * FROM tasks ORDER BY created_at, task_id")
    try:
        for row in cursor:
            yield Task.model_validate(dict(row))
    finally:
        cursor.close()


def iter_attempts(connection: sqlite3.Connection, task_id: str) -> Iterator[Attempt]:
    cursor = connection.execute(
        "SELECT * FROM attempts WHERE task_id = ? ORDER BY started_at", (task_id,)
    )
    try:
        for row in cursor:
            yield Attempt.model_validate(dict(row))
    finally:
        cursor.close()


def claim_task(connection: sqlite3.Connection) -> Task | None:
    """Claim one ready task and record its attempt in the same transaction."""
    with transaction(connection):
        row = connection.execute(
            """
            SELECT tasks.* FROM tasks
            WHERE tasks.status = ? AND NOT EXISTS (
                SELECT 1 FROM dependencies
                JOIN tasks AS prerequisite ON prerequisite.task_id = depends_on
                WHERE dependencies.task_id = tasks.task_id AND prerequisite.status != ?
            )
            ORDER BY tasks.created_at, tasks.task_id
            LIMIT 1
            """,
            (STATUS_PENDING, STATUS_SUCCEEDED),
        ).fetchone()
        if row is None:
            return None

        task = Task.model_validate(dict(row))
        token = uuid4().hex
        now = datetime.now(UTC).isoformat()
        connection.execute(
            """
            UPDATE tasks SET status = ?, attempt_token = ?,
                attempt_count = attempt_count + 1, failure_code = NULL, updated_at = ?
            WHERE task_id = ?
            """,
            (STATUS_RUNNING, token, now, task.task_id),
        )
        connection.execute(
            """
            INSERT INTO attempts (task_id, attempt_token, status, started_at)
            VALUES (?, ?, ?, ?)
            """,
            (task.task_id, token, STATUS_RUNNING, now),
        )

    return get_task(connection, task.task_id)


def require_attempt(connection: sqlite3.Connection, claimed: Task) -> Task:
    """Reject stale workers before accepting their state or result."""
    current = get_task(connection, claimed.task_id)
    if (
        current.status != STATUS_RUNNING
        or claimed.attempt_token is None
        or current.attempt_token != claimed.attempt_token
    ):
        raise ValueError(ERROR_STALE_ATTEMPT)
    return current


def complete_task(
    connection: sqlite3.Connection,
    claimed: Task,
    *,
    result: Artifact | None = None,
    successors: Sequence[TaskSpec] = (),
) -> Task:
    """Accept a result once and enqueue successors atomically.

    The durability layer must persist and validate an artifact before calling this
    function. Metadata-only steps can complete without a file. This is not publish.
    """
    with transaction(connection):
        current = get_task(connection, claimed.task_id)
        if (
            current.status == STATUS_SUCCEEDED
            and claimed.attempt_token is not None
            and current.attempt_token == claimed.attempt_token
        ):
            expected = (
                result.path if result else None,
                result.sha256 if result else None,
                result.size if result else None,
            )
            if (
                current.result_path,
                current.result_sha256,
                current.result_size,
            ) != expected:
                raise ValueError(ERROR_COMPLETION_CHANGED)
            for successor in successors:
                if (
                    connection.execute(
                        "SELECT task_id FROM tasks WHERE task_id = ?",
                        (successor.task_id,),
                    ).fetchone()
                    is None
                ):
                    raise ValueError(ERROR_COMPLETION_CHANGED)
                _insert_task(connection, successor, (claimed.task_id,))
            return current

        require_attempt(connection, claimed)
        now = datetime.now(UTC).isoformat()
        connection.execute(
            """
            UPDATE tasks SET status = ?, updated_at = ?,
                result_path = ?, result_sha256 = ?, result_size = ?
            WHERE task_id = ?
            """,
            (
                STATUS_SUCCEEDED,
                now,
                str(result.path) if result else None,
                result.sha256 if result else None,
                result.size if result else None,
                claimed.task_id,
            ),
        )
        connection.execute(
            "UPDATE attempts SET status = ?, finished_at = ? WHERE attempt_token = ?",
            (STATUS_SUCCEEDED, now, claimed.attempt_token),
        )
        for successor in successors:
            _insert_task(connection, successor, (claimed.task_id,))

    return get_task(connection, claimed.task_id)


def fail_task(connection: sqlite3.Connection, claimed: Task, code: str) -> Task:
    """Persist only registered reason codes, never arbitrary exception messages."""
    if code not in FAILURE_CODES:
        raise ValueError(ERROR_INVALID_FAILURE_CODE)

    with transaction(connection):
        require_attempt(connection, claimed)
        now = datetime.now(UTC).isoformat()
        connection.execute(
            """
            UPDATE tasks SET status = ?, failure_code = ?, updated_at = ?
            WHERE task_id = ?
            """,
            (STATUS_FAILED, code, now, claimed.task_id),
        )
        connection.execute(
            """
            UPDATE attempts SET status = ?, failure_code = ?, finished_at = ?
            WHERE attempt_token = ?
            """,
            (STATUS_FAILED, code, now, claimed.attempt_token),
        )

    return get_task(connection, claimed.task_id)


def retry_task(connection: sqlite3.Connection, task_id: str) -> Task:
    """Retry an explicitly failed task; ordinary rediscovery never retries it."""
    with transaction(connection):
        if get_task(connection, task_id).status != STATUS_FAILED:
            raise ValueError(ERROR_INVALID_TRANSITION)
        connection.execute(
            """
            UPDATE tasks SET status = ?, attempt_token = NULL,
                failure_code = NULL, updated_at = ? WHERE task_id = ?
            """,
            (STATUS_PENDING, datetime.now(UTC).isoformat(), task_id),
        )
    return get_task(connection, task_id)


def recover_interrupted(connection: sqlite3.Connection) -> int:
    """Only call under exclusive coordinator ownership, before dispatching work."""
    with transaction(connection):
        now = datetime.now(UTC).isoformat()
        connection.execute(
            """
            UPDATE attempts SET status = ?, finished_at = ?, failure_code = ?
            WHERE status = ?
            """,
            (STATUS_INTERRUPTED, now, ERROR_INTERRUPTED, STATUS_RUNNING),
        )
        count = connection.execute(
            """
            UPDATE tasks SET status = ?, attempt_token = NULL, updated_at = ?
            WHERE status = ?
            """,
            (STATUS_PENDING, now, STATUS_RUNNING),
        ).rowcount
    return count
