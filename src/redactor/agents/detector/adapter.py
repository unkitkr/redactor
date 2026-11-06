"""Freeze analysis observations and replay them without calling a model again."""

import sqlite3

import httpx

from redactor.agents.detector.detect import detect_text
from redactor.inference.cache import cache_ner
from redactor.persistence.files.registration import prepare_successor
from redactor.persistence.models.observations import (
    read_detection_observation,
    save_detection_observation,
)
from redactor.schemas.configuration import PipelineSettings
from redactor.schemas.entities import EntityDetection, NerAdapter, TextEntity
from redactor.schemas.persistence import Task
from redactor.utils.constants import MODEL_LOCAL, MODEL_PURPOSE_DETECTOR, STEP_ANALYZE
from redactor.utils.errors import ERROR_COVERAGE, ERROR_MODEL_DISABLED


def detection_adapter(
    connection: sqlite3.Connection,
    task: Task,
    *,
    settings: PipelineSettings,
    mapping_key: bytes,
    local_ner: NerAdapter,
    transport: httpx.AsyncBaseTransport | None = None,
) -> NerAdapter:
    """Only analysis can create observations; later steps consume frozen evidence.

    Verification uses this adapter to reconstruct the intended edits, then scans
    original and saved text independently with its own local adapter. A saved
    detector result never authorizes publication.
    """
    analysis_id = (
        task.task_id
        if task.step == STEP_ANALYZE
        else prepare_successor(connection, task, STEP_ANALYZE).task_id
    )

    def recognize(text: str) -> tuple[TextEntity, ...]:
        previous = read_detection_observation(
            connection, analysis_id, text, mapping_key
        )
        if previous is not None:
            return previous.entities
        if task.step != STEP_ANALYZE:
            raise ValueError(ERROR_COVERAGE)

        if text.strip():
            # The provider replays an accepted response before checking availability.
            # This also covers a crash between saving a response and its observation.
            detection = detect_text(
                connection,
                task,
                text,
                MODEL_PURPOSE_DETECTOR,
                settings=settings,
                mapping_key=mapping_key,
                local_ner=local_ner,
                transport=transport,
            )
        else:
            detection = EntityDetection(
                entities=local_ner(text),
                backend=MODEL_LOCAL,
                fallback_reason=ERROR_MODEL_DISABLED,
            )
        return save_detection_observation(
            connection, task, text, detection, mapping_key
        ).entities

    return cache_ner(
        recognize,
        maximum_entries=settings.local.ner_cache_entries,
        maximum_text_characters=settings.local.ner_cache_characters,
    )
