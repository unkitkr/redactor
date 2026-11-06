"""Use replayable remote observations or a bounded local adapter on the same text."""

import sqlite3
from collections.abc import Mapping

import httpx

from redactor.agents.detector.prompts import detection_request
from redactor.inference.evidence import validate_entity_evidence
from redactor.schemas.configuration import PipelineSettings
from redactor.schemas.entities import EntityDetection, NerAdapter, TextEntities
from redactor.schemas.persistence import Task
from redactor.utils.constants import MODEL_LOCAL, MODEL_REMOTE
from redactor.utils.errors import (
    ERROR_ENTITY_EVIDENCE,
    ERROR_LOCAL_INFERENCE,
    ERROR_LOCAL_UNAVAILABLE,
)
from redactor.utils.provider import request_json


def detect_text(
    connection: sqlite3.Connection,
    claimed: Task,
    text: str,
    context_id: str,
    *,
    settings: PipelineSettings,
    mapping_key: bytes,
    local_ner: NerAdapter,
    environment: Mapping[str, str] | None = None,
    transport: httpx.AsyncBaseTransport | None = None,
) -> EntityDetection:
    """Return grounded observations, not proof that the text contains no other PHI.

    The analysis caller persists these observations with its complete-record cursor.
    A failed local adapter must remain an error, never an empty successful detection.
    """
    decision = request_json(
        connection,
        claimed,
        settings,
        detection_request(text, context_id),
        TextEntities,
        mapping_key,
        environment=environment,
        transport=transport,
    )
    reason = decision.reason_code
    if decision.backend == MODEL_REMOTE:
        try:
            entities = validate_entity_evidence(
                text, TextEntities.model_validate(decision.payload)
            )
        except ValueError:
            reason = ERROR_ENTITY_EVIDENCE
        else:
            return EntityDetection(entities=entities, backend=MODEL_REMOTE)

    try:
        local_result = TextEntities(entities=local_ner(text))
    except Exception as error:
        # Adapters may expose input text in exceptions. Keep that out of run logs.
        if isinstance(error, ValueError) and error.args == (ERROR_LOCAL_UNAVAILABLE,):
            raise ValueError(ERROR_LOCAL_UNAVAILABLE) from None
        raise ValueError(ERROR_LOCAL_INFERENCE) from None
    entities = validate_entity_evidence(text, local_result)
    return EntityDetection(
        entities=entities, backend=MODEL_LOCAL, fallback_reason=reason
    )
