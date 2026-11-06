"""Extract all image frames before redacting their text, barcodes and faces."""

import sqlite3
from collections import Counter
from pathlib import Path
from tempfile import TemporaryDirectory

from redactor.formats.images import pixel_digest, read_image_frames
from redactor.inference.adapters.barcodes import locate_barcodes
from redactor.inference.adapters.faces import load_face_detector
from redactor.persistence.files.artifacts import inspect_artifact
from redactor.persistence.files.results import write_step_result
from redactor.persistence.identities.observations import save_observation_batch
from redactor.policy.pixels import text_pixel_masks
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
    PIXEL_PNG_FORMAT,
    PIXEL_TEMPORARY_FILENAME,
    YUNET_DIRECTORY,
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
        frames = read_image_frames(task.input_path, settings.resources)
        faces = load_face_detector(settings.local.model_directory / YUNET_DIRECTORY)
        with TemporaryDirectory() as temporary:
            path = Path(temporary) / PIXEL_TEMPORARY_FILENAME
            # Finish OCR before loading NER; both models need not reside together.
            for frame in frames:
                frame.save(path, format=PIXEL_PNG_FORMAT)
                assessed.append(
                    PixelFrame(
                        width=frame.width,
                        height=frame.height,
                        sha256=pixel_digest(frame),
                        regions=local_ocr(path),
                        masks=locate_barcodes(path) + faces(path),
                    )
                )
        for index, evidence in enumerate(assessed):
            masks, findings = text_pixel_masks(
                evidence.regions, (evidence.width, evidence.height), detector
            )
            counts.update(findings)
            counts.update(mask.kind for mask in evidence.masks)
            assessed[index] = evidence.model_copy(
                update={"masks": evidence.masks + masks}
            )
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
