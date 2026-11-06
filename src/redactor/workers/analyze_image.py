"""Extract all image frames before redacting their text, barcodes and faces."""

import sqlite3
from collections import Counter

from redactor.inference.images import analyze_image_content
from redactor.persistence.files.artifacts import inspect_artifact
from redactor.persistence.files.results import write_step_result
from redactor.persistence.identities.observations import save_observation_batch
from redactor.schemas.analysis import FileAnalysis
from redactor.schemas.configuration import PipelineSettings
from redactor.schemas.entities import NerAdapter
from redactor.schemas.formats import FileInspection
from redactor.schemas.ocr import OcrAdapter
from redactor.schemas.persistence import Task
from redactor.schemas.pipeline import StepResult
from redactor.schemas.pixels import PixelFrame
from redactor.utils.constants import (
    ENCRYPTION_HEADER,
    ENCRYPTION_NONCE_BYTES,
    ENCRYPTION_TAG_BYTES,
    MAX_MANIFEST_BYTES,
)
from redactor.utils.errors import ERROR_INPUT_CHANGED, ERROR_RESOURCE_LIMIT
from redactor.utils.failures import failure_reason


def analyze_image_task(
    connection: sqlite3.Connection,
    task: Task,
    inspection: FileInspection,
    *,
    settings: PipelineSettings,
    mapping_key: bytes,
    detector: NerAdapter,
    local_ocr: OcrAdapter,
) -> StepResult:
    assessed: list[PixelFrame] = []
    counts: Counter[str] = Counter()
    reason = None
    try:
        before = inspect_artifact(task.input_path, persist=False)
        if before.sha256 != task.input_sha256 or before.size != task.input_size:
            raise ValueError(ERROR_INPUT_CHANGED)
        frames, findings = analyze_image_content(
            task.input_path, settings, detector, local_ocr
        )
        assessed = list(frames)
        counts.update(findings)
        summary = FileAnalysis(
            file_type=inspection.file_type,
            record_count=len(assessed),
            images=tuple(assessed),
            counts=dict(counts),
        )
        encrypted_size = (
            len(summary.model_dump_json().encode())
            + len(ENCRYPTION_HEADER)
            + ENCRYPTION_NONCE_BYTES
            + ENCRYPTION_TAG_BYTES
        )
        if encrypted_size > MAX_MANIFEST_BYTES:
            raise ValueError(ERROR_RESOURCE_LIMIT)
        if inspect_artifact(task.input_path, persist=False) != before:
            raise ValueError(ERROR_INPUT_CHANGED)
        save_observation_batch(
            connection,
            task,
            (),
            mapping_key,
            sequence=1,
            input_offset=task.input_size,
            record_count=len(assessed),
            counts=dict(counts),
        )
    except Exception as error:
        reason = failure_reason(error)
    summary = FileAnalysis(
        file_type=inspection.file_type,
        record_count=len(assessed),
        reason=reason,
        images=tuple(assessed) if reason is None else (),
        counts=dict(counts),
    )
    return StepResult(
        artifact=write_step_result(
            connection, task, summary, encryption_key=mapping_key
        )
    )
