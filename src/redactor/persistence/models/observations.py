"""Freeze grounded detector results for analysis retries and later pipeline steps."""

import hmac
import json
import sqlite3

from redactor.inference.evidence import validate_entity_evidence
from redactor.persistence.database import transaction
from redactor.persistence.queue.tasks import require_attempt
from redactor.schemas.entities import EntityDetection
from redactor.schemas.persistence import Task
from redactor.utils.constants import (
    DETECTOR_OBSERVATION_CONTEXT,
    JSON_SEPARATORS,
    SECRET_KEY_BYTES,
    STEP_ANALYZE,
    TEXT_ENCODING,
)
from redactor.utils.encryption import decrypt_payload, encrypt_payload
from redactor.utils.errors import ERROR_PRIVATE_RECORD, ERROR_STEP_RESULT


def read_detection_observation(
    connection: sqlite3.Connection,
    analysis_task_id: str,
    text: str,
    mapping_key: bytes,
) -> EntityDetection | None:
    """Read the accepted observation without storing or indexing the original text."""
    observation_key = _observation_key(analysis_task_id, text, mapping_key)
    row = connection.execute(
        "SELECT encrypted_payload FROM detection_observations "
        "WHERE task_id = ? AND observation_key = ?",
        (analysis_task_id, observation_key),
    ).fetchone()
    if row is None:
        return None
    payload = decrypt_payload(
        mapping_key,
        row[0],
        context=DETECTOR_OBSERVATION_CONTEXT + observation_key.encode(TEXT_ENCODING),
    )
    return _validated_detection(text, payload)


def save_detection_observation(
    connection: sqlite3.Connection,
    claimed: Task,
    text: str,
    detection: EntityDetection,
    mapping_key: bytes,
) -> EntityDetection:
    """Accept one result per exact text, only from the current analysis attempt.

    Completed remote responses and actual local fallback results share this store.
    A retry returns the accepted result even if a new detector answer differs.
    """
    observation_key = _observation_key(claimed.task_id, text, mapping_key)
    serialized = detection.model_dump_json().encode(TEXT_ENCODING)
    accepted = _validated_detection(text, serialized)
    encrypted_payload = encrypt_payload(
        mapping_key,
        serialized,
        context=DETECTOR_OBSERVATION_CONTEXT + observation_key.encode(TEXT_ENCODING),
    )
    with transaction(connection):
        current = require_attempt(connection, claimed)
        if current.step != STEP_ANALYZE:
            raise ValueError(ERROR_STEP_RESULT)
        previous = read_detection_observation(
            connection, current.task_id, text, mapping_key
        )
        if previous is not None:
            return previous
        connection.execute(
            "INSERT INTO detection_observations "
            "(task_id, observation_key, encrypted_payload) VALUES (?, ?, ?)",
            (current.task_id, observation_key, encrypted_payload),
        )
    return accepted


def _observation_key(analysis_task_id: str, text: str, mapping_key: bytes) -> str:
    if len(mapping_key) != SECRET_KEY_BYTES or not analysis_task_id:
        raise ValueError(ERROR_PRIVATE_RECORD)
    payload = json.dumps(
        (analysis_task_id, text), separators=JSON_SEPARATORS, ensure_ascii=False
    ).encode(TEXT_ENCODING)
    return hmac.digest(
        mapping_key, DETECTOR_OBSERVATION_CONTEXT + payload, "sha256"
    ).hex()


def _validated_detection(text: str, payload: bytes) -> EntityDetection:
    try:
        detection = EntityDetection.model_validate_json(payload)
        validate_entity_evidence(text, detection)
    except ValueError:
        raise ValueError(ERROR_PRIVATE_RECORD) from None
    return detection
