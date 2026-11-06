"""Reserve every possible charge before network I/O, including retries."""

import sqlite3
import time

from redactor.persistence.database import transaction
from redactor.persistence.queue import require_attempt
from redactor.schemas.configuration import RemoteSettings
from redactor.schemas.persistence import Task
from redactor.schemas.provider import ModelReservation, ModelUnavailable, ModelUsage
from redactor.utils.constants import (
    MODEL_RESERVED,
    MODEL_SETTLED,
    MODEL_UNCERTAIN,
)
from redactor.utils.errors import (
    ERROR_MODEL_ACCOUNTING,
    ERROR_MODEL_ATTEMPTS,
    ERROR_MODEL_BUDGET,
    ERROR_MODEL_BUSY,
    ERROR_MODEL_CIRCUIT,
    ERROR_MODEL_PRICE_BOUND,
)


def reserve_attempt(
    connection: sqlite3.Connection,
    claimed: Task,
    request_key: str,
    maximum_cost_nanos: int,
    budget_nanos: int,
    settings: RemoteSettings,
) -> ModelReservation | ModelUnavailable:
    if maximum_cost_nanos < 0 or budget_nanos < 0:
        raise ValueError(ERROR_MODEL_ACCOUNTING)
    with transaction(connection):
        require_attempt(connection, claimed)
        connection.execute(
            "INSERT INTO model_circuits(processing_version) VALUES (?) "
            "ON CONFLICT DO NOTHING",
            (claimed.processing_version,),
        )
        circuit = connection.execute(
            "SELECT * FROM model_circuits WHERE processing_version = ?",
            (claimed.processing_version,),
        ).fetchone()
        if circuit["disabled_reason"] is not None:
            return ModelUnavailable(reason_code=circuit["disabled_reason"])
        if (
            circuit["retry_after"] > time.time()
            or circuit["probe_attempt_id"] is not None
        ):
            return ModelUnavailable(reason_code=ERROR_MODEL_CIRCUIT)
        attempts = connection.execute(
            "SELECT count(*) AS total, count(*) FILTER (WHERE status = ?) AS active "
            "FROM model_attempts WHERE request_key = ?",
            (MODEL_RESERVED, request_key),
        ).fetchone()
        if attempts["active"]:
            return ModelUnavailable(reason_code=ERROR_MODEL_BUSY)
        if attempts["total"] >= settings.max_attempts:
            return ModelUnavailable(reason_code=ERROR_MODEL_ATTEMPTS)
        spent = accounted_cost(connection, claimed.processing_version)
        if spent + maximum_cost_nanos > budget_nanos:
            return ModelUnavailable(reason_code=ERROR_MODEL_BUDGET)
        cursor = connection.execute(
            """
            INSERT INTO model_attempts (
                request_key, task_id, task_attempt_token, reserved_nanos, status
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (
                request_key,
                claimed.task_id,
                claimed.attempt_token,
                maximum_cost_nanos,
                MODEL_RESERVED,
            ),
        )
        assert cursor.lastrowid is not None
        if circuit["failures"] >= settings.circuit_failures:
            connection.execute(
                "UPDATE model_circuits SET probe_attempt_id = ? "
                "WHERE processing_version = ?",
                (cursor.lastrowid, claimed.processing_version),
            )
        return ModelReservation(
            attempt_id=cursor.lastrowid,
            request_key=request_key,
            reserved_nanos=maximum_cost_nanos,
        )


def settle_attempt(
    connection: sqlite3.Connection,
    claimed: Task,
    reservation: ModelReservation,
    usage: ModelUsage | None,
) -> None:
    """No receipt means the entire reservation remains counted as possibly billed."""
    with transaction(connection):
        require_attempt(connection, claimed)
        updated = connection.execute(
            """
            UPDATE model_attempts SET status = ?, charged_nanos = ?,
                input_tokens = ?, output_tokens = ?
            WHERE attempt_id = ? AND request_key = ? AND task_id = ?
                AND task_attempt_token = ? AND reserved_nanos = ? AND status = ?
            """,
            (
                MODEL_SETTLED if usage is not None else MODEL_UNCERTAIN,
                usage.cost_nanos if usage is not None else None,
                usage.input_tokens if usage is not None else None,
                usage.output_tokens if usage is not None else None,
                reservation.attempt_id,
                reservation.request_key,
                claimed.task_id,
                claimed.attempt_token,
                reservation.reserved_nanos,
                MODEL_RESERVED,
            ),
        ).rowcount
        if updated != 1:
            raise ValueError(ERROR_MODEL_ACCOUNTING)
        if usage is not None and usage.cost_nanos > reservation.reserved_nanos:
            connection.execute(
                "UPDATE model_circuits SET disabled_reason = ? "
                "WHERE processing_version = ?",
                (ERROR_MODEL_PRICE_BOUND, claimed.processing_version),
            )


def accounted_cost(connection: sqlite3.Connection, processing_version: str) -> int:
    row = connection.execute(
        """
        SELECT COALESCE(sum(COALESCE(charged_nanos, reserved_nanos)), 0)
        FROM model_attempts JOIN tasks USING(task_id) WHERE processing_version = ?
        """,
        (processing_version,),
    ).fetchone()
    return int(row[0])


def recover_model_attempts(connection: sqlite3.Connection) -> None:
    """Call under exclusive coordinator ownership after all old workers have died."""
    with transaction(connection):
        connection.execute(
            "UPDATE model_attempts SET status = ? WHERE status = ?",
            (MODEL_UNCERTAIN, MODEL_RESERVED),
        )
        connection.execute("UPDATE model_circuits SET probe_attempt_id = NULL")
