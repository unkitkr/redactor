"""Rescore historical encrypted responses without requests or ledger mutations.

Historical fingerprints belong only to evaluation. Production request identity,
fencing, and cache invalidation remain unchanged.
"""

import hashlib
import hmac
import json
import sqlite3
from collections.abc import Callable, Generator
from contextlib import contextmanager
from pathlib import Path

from redactor.agents.detector.prompts import detection_request
from redactor.evaluation.remote import remote_settings
from redactor.inference.evidence import validate_entity_evidence
from redactor.persistence.files.registration import prepare_task
from redactor.persistence.models.decisions import read_model_decision
from redactor.persistence.queue.tasks import get_task
from redactor.schemas.configuration import PipelineSettings
from redactor.schemas.entities import NerAdapter, TextEntities, TextEntity
from redactor.schemas.persistence import Task
from redactor.schemas.provider import ModelRequest
from redactor.utils.configuration import key_fingerprint
from redactor.utils.constants import (
    DATABASE_FILENAME,
    EVALUATION_KEY_FILENAME,
    EVALUATION_REMOTE_VERSION,
    EVALUATION_REPLAY_HIT,
    EVALUATION_REPLAY_LOCAL,
    EVALUATION_REPLAY_MISS,
    EVALUATION_REPLAY_REMOTE,
    JSON_SEPARATORS,
    MODEL_REMOTE,
    MODEL_REQUEST_CONTEXT,
    TEXT_ENCODING,
)
from redactor.utils.errors import (
    ERROR_EVALUATION_CACHE_MISS,
    ERROR_MODEL_RESPONSE,
)


@contextmanager
def replay_state(
    directory: Path, source: Path, step: str
) -> Generator[tuple[sqlite3.Connection, Task, bytes], None, None]:
    """Read a consistent existing ledger without migration, recovery, or claiming."""
    database = (directory / DATABASE_FILENAME).resolve(strict=True)
    mapping_key = (directory / EVALUATION_KEY_FILENAME).read_bytes()
    key_fingerprint(mapping_key)
    expected = prepare_task(source, step, EVALUATION_REMOTE_VERSION)
    connection = sqlite3.connect(database.as_uri() + "?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        connection.execute("PRAGMA query_only = ON")
        connection.execute("BEGIN")
        task = get_task(connection, expected.task_id)
        yield connection, task, mapping_key
    finally:
        connection.rollback()
        connection.close()


def load_replay_ner(
    connection: sqlite3.Connection,
    task: Task,
    model: str,
    mapping_key: bytes,
    processing_version: str,
    record_event: Callable[[str], None],
) -> NerAdapter:
    """A missing historical decision is an explicit fallback, never a new request."""
    settings = remote_settings(model)
    key_fingerprint(mapping_key)

    def recognize(text: str) -> tuple[TextEntity, ...]:
        context = hashlib.sha256(text.encode(TEXT_ENCODING)).hexdigest()
        request_key = _historical_request_key(
            task,
            settings,
            detection_request(text, context),
            mapping_key,
            processing_version,
        )
        decision = read_model_decision(connection, request_key, mapping_key)
        if decision is None:
            record_event(EVALUATION_REPLAY_MISS)
            raise ValueError(ERROR_EVALUATION_CACHE_MISS)
        record_event(EVALUATION_REPLAY_HIT)
        if decision.backend != MODEL_REMOTE:
            record_event(EVALUATION_REPLAY_LOCAL)
            raise ValueError(decision.reason_code or ERROR_MODEL_RESPONSE)
        entities = validate_entity_evidence(
            text, TextEntities.model_validate(decision.payload)
        )
        record_event(EVALUATION_REPLAY_REMOTE)
        return entities

    return recognize


def _historical_request_key(
    task: Task,
    settings: PipelineSettings,
    request: ModelRequest,
    mapping_key: bytes,
    processing_version: str,
) -> str:
    """Reproduce the recorded identity while keeping all other inputs exact."""
    processing = settings.model_dump(mode="json")
    del processing["remote"]["enabled"]
    fingerprint = hashlib.sha256(
        json.dumps(
            (processing_version, processing),
            sort_keys=True,
            separators=JSON_SEPARATORS,
        ).encode(TEXT_ENCODING)
    ).hexdigest()
    identity = json.dumps(
        (
            task.task_id,
            fingerprint,
            request.model_dump(),
            TextEntities.model_json_schema(),
        ),
        sort_keys=True,
        separators=JSON_SEPARATORS,
    ).encode(TEXT_ENCODING)
    return hmac.digest(mapping_key, MODEL_REQUEST_CONTEXT + identity, "sha256").hex()
