"""Keep a logical request's deadline and pending wait across worker restarts."""

import sqlite3
import time

from redactor.persistence.database import transaction
from redactor.persistence.queue.tasks import require_attempt
from redactor.schemas.persistence import Task
from redactor.schemas.provider import ModelRequestWindow
from redactor.utils.errors import ERROR_MODEL_ACCOUNTING


def request_window(
    connection: sqlite3.Connection,
    claimed: Task,
    request_key: str,
    deadline_seconds: float,
) -> ModelRequestWindow:
    with transaction(connection):
        require_attempt(connection, claimed)
        connection.execute(
            "INSERT INTO model_request_windows(request_key, task_id, deadline_at) "
            "VALUES (?, ?, ?) ON CONFLICT DO NOTHING",
            (request_key, claimed.task_id, time.time() + deadline_seconds),
        )
        row = connection.execute(
            "SELECT * FROM model_request_windows WHERE request_key = ?",
            (request_key,),
        ).fetchone()
        if row["task_id"] != claimed.task_id:
            raise ValueError(ERROR_MODEL_ACCOUNTING)
        attempts = connection.execute(
            "SELECT count(*) FROM model_attempts WHERE request_key = ?",
            (request_key,),
        ).fetchone()[0]
        return ModelRequestWindow(
            deadline_at=row["deadline_at"],
            retry_after_at=row["retry_after_at"],
            attempts_used=attempts,
        )


def defer_request(
    connection: sqlite3.Connection,
    claimed: Task,
    request_key: str,
    delay_seconds: float,
) -> None:
    with transaction(connection):
        require_attempt(connection, claimed)
        updated = connection.execute(
            "UPDATE model_request_windows SET retry_after_at = ? "
            "WHERE request_key = ? AND task_id = ?",
            (time.time() + delay_seconds, request_key, claimed.task_id),
        ).rowcount
        if updated != 1:
            raise ValueError(ERROR_MODEL_ACCOUNTING)
