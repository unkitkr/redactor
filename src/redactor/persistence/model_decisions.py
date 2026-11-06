"""Replay encrypted model answers and fallback choices, with shared circuit state."""

import sqlite3
import time

from redactor.persistence.database import transaction
from redactor.persistence.queue import require_attempt
from redactor.schemas.configuration import RemoteSettings
from redactor.schemas.persistence import Task
from redactor.schemas.provider import ModelDecision
from redactor.utils.constants import MODEL_LOCAL, MODEL_REMOTE
from redactor.utils.encryption import decrypt_payload, encrypt_payload
from redactor.utils.errors import ERROR_PRIVATE_RECORD, MODEL_REASON_CODES


def read_model_decision(
    connection: sqlite3.Connection, request_key: str, encryption_key: bytes
) -> ModelDecision | None:
    row = connection.execute(
        "SELECT encrypted_payload FROM model_decisions WHERE request_key = ?",
        (request_key,),
    ).fetchone()
    if row is None:
        return None
    payload = decrypt_payload(encryption_key, row[0], context=request_key.encode())
    try:
        return ModelDecision.model_validate_json(payload)
    except ValueError:
        raise ValueError(ERROR_PRIVATE_RECORD) from None


def save_model_decision(
    connection: sqlite3.Connection,
    claimed: Task,
    request_key: str,
    decision: ModelDecision,
    encryption_key: bytes,
    settings: RemoteSettings,
    *,
    transient_failure: bool = False,
    disable_remote: bool = False,
) -> ModelDecision:
    """Accept the first decision before exposing it to a detector or a judge."""
    if decision.backend == MODEL_LOCAL:
        if (
            decision.reason_code not in MODEL_REASON_CODES
            or decision.payload is not None
        ):
            raise ValueError(ERROR_PRIVATE_RECORD)
    elif decision.payload is None or decision.reason_code is not None:
        raise ValueError(ERROR_PRIVATE_RECORD)
    payload = encrypt_payload(
        encryption_key,
        decision.model_dump_json().encode(),
        context=request_key.encode(),
    )
    with transaction(connection):
        require_attempt(connection, claimed)
        previous = read_model_decision(connection, request_key, encryption_key)
        if previous is not None:
            return previous
        connection.execute(
            "INSERT INTO model_decisions(request_key, task_id, encrypted_payload) "
            "VALUES (?, ?, ?)",
            (request_key, claimed.task_id, payload),
        )
        connection.execute(
            "INSERT INTO model_circuits(processing_version) VALUES (?) "
            "ON CONFLICT DO NOTHING",
            (claimed.processing_version,),
        )
        if decision.backend == MODEL_REMOTE:
            connection.execute(
                "UPDATE model_circuits SET failures = 0, retry_after = 0, "
                "probe_attempt_id = NULL WHERE processing_version = ?",
                (claimed.processing_version,),
            )
        elif transient_failure:
            connection.execute(
                """
                UPDATE model_circuits SET failures = failures + 1,
                    retry_after = CASE WHEN failures + 1 >= ? THEN ? ELSE 0 END,
                    probe_attempt_id = NULL
                WHERE processing_version = ?
                """,
                (
                    settings.circuit_failures,
                    time.time() + settings.circuit_cooldown_seconds,
                    claimed.processing_version,
                ),
            )
        if disable_remote:
            connection.execute(
                "UPDATE model_circuits SET disabled_reason = ?, "
                "probe_attempt_id = NULL "
                "WHERE processing_version = ?",
                (decision.reason_code, claimed.processing_version),
            )
    return decision
