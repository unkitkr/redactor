"""Reopen images, check every pixel and independently OCR the source and output."""

import sqlite3
from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np
from PIL import Image

from redactor.formats.images import encode_image_frames, pixel_digest, read_image_frames
from redactor.inference.adapters.barcodes import locate_barcodes
from redactor.inference.adapters.faces import load_face_detector
from redactor.inference.adapters.tesseract import load_tesseract
from redactor.inference.ocr_evidence import validate_ocr_regions
from redactor.persistence.files.artifacts import inspect_artifact
from redactor.persistence.files.registration import prepare_successor
from redactor.persistence.files.results import read_step_result
from redactor.policy.pixels import intersects, located_words, scan_image_text
from redactor.schemas.analysis import FileAnalysis
from redactor.schemas.configuration import PipelineSettings
from redactor.schemas.entities import NerAdapter
from redactor.schemas.ocr import OcrRegion
from redactor.schemas.persistence import Artifact, Task
from redactor.schemas.pixels import PixelFrame
from redactor.schemas.verification import VerificationCheck
from redactor.utils.constants import (
    CHECK_PIXELS,
    OCR_TESSDATA_DIRECTORY,
    PIXEL_MASK_COLOR,
    PIXEL_PNG_FORMAT,
    PIXEL_TEMPORARY_FILENAME,
    REQUIRED_VERIFICATION_CHECKS,
    STEP_ANALYZE,
    VERIFICATION_PASS,
    YUNET_DIRECTORY,
)
from redactor.utils.errors import (
    ERROR_ARTIFACT_CORRUPT,
    ERROR_CLINICAL_CHANGED,
    ERROR_COVERAGE,
    ERROR_PIXELS,
)
from redactor.verification.residuals import protected_clinical_ranges


def verify_images(
    connection: sqlite3.Connection,
    task: Task,
    artifact: Artifact,
    *,
    settings: PipelineSettings,
    mapping_key: bytes,
    local_ner: NerAdapter,
) -> tuple[VerificationCheck, ...]:
    original = inspect_artifact(task.input_path, persist=False)
    if (
        original.sha256 != task.input_sha256
        or original.size != task.input_size
        or inspect_artifact(artifact.path, persist=False) != artifact
    ):
        raise ValueError(ERROR_ARTIFACT_CORRUPT)
    analysis = read_step_result(
        connection,
        prepare_successor(connection, task, STEP_ANALYZE).task_id,
        FileAnalysis,
        encryption_key=mapping_key,
    )
    if analysis.reason is not None:
        raise ValueError(ERROR_COVERAGE)
    frames = verify_image_content(
        task.input_path,
        artifact.path,
        analysis.images,
        analysis.file_type.upper(),
        settings,
        local_ner,
    )
    if (
        inspect_artifact(task.input_path, persist=False) != original
        or inspect_artifact(artifact.path, persist=False) != artifact
    ):
        raise ValueError(ERROR_ARTIFACT_CORRUPT)
    return tuple(
        VerificationCheck(
            kind=kind,
            status=VERIFICATION_PASS,
            expected=frames,
            checked=frames,
        )
        for kind in (*REQUIRED_VERIFICATION_CHECKS, CHECK_PIXELS)
    )


def verify_image_content(
    original_path: Path,
    output_path: Path,
    evidence_frames: tuple[PixelFrame, ...],
    image_format: str,
    settings: PipelineSettings,
    local_ner: NerAdapter,
) -> int:
    source = read_image_frames(original_path, settings.resources)
    output = read_image_frames(output_path, settings.resources)
    if not source or not len(source) == len(output) == len(evidence_frames):
        raise ValueError(ERROR_COVERAGE)
    expected: list[Image.Image] = []
    for before, evidence in zip(source, evidence_frames, strict=True):
        if (
            before.size != (evidence.width, evidence.height)
            or pixel_digest(before) != evidence.sha256
        ):
            raise ValueError(ERROR_ARTIFACT_CORRUPT)
        pixels = np.array(before, copy=True)
        for mask in evidence.masks:
            left, top, right, bottom = mask.box
            if not (
                0 <= left < right <= before.width and 0 <= top < bottom <= before.height
            ):
                raise ValueError(ERROR_PIXELS)
            pixels[top:bottom, left:right] = PIXEL_MASK_COLOR
        expected.append(Image.fromarray(pixels))
    # Fresh, independently constructed pixels also bind metadata and trailing
    # bytes. JPEG comparison includes the declared deterministic codec loss.
    if output_path.read_bytes() != encode_image_frames(tuple(expected), image_format):
        raise ValueError(ERROR_PIXELS)
    faces = load_face_detector(settings.local.model_directory / YUNET_DIRECTORY)
    source_ocr = load_tesseract(
        settings.local.model_directory / OCR_TESSDATA_DIRECTORY,
        settings.local.ocr_language,
        word_boxes=True,
    )
    saved_ocr = load_tesseract(
        settings.local.model_directory / OCR_TESSDATA_DIRECTORY,
        settings.local.ocr_language,
        word_boxes=True,
        allow_empty=True,
    )
    with TemporaryDirectory() as temporary:
        path = Path(temporary) / PIXEL_TEMPORARY_FILENAME
        for before, after, evidence in zip(
            source, output, evidence_frames, strict=True
        ):
            before.save(path, format=PIXEL_PNG_FORMAT)
            regions = validate_ocr_regions(source_ocr(path), before.size)
            _verify_source_regions(regions, evidence, local_ner)
            after.save(path, format=PIXEL_PNG_FORMAT)
            if locate_barcodes(path) or faces(path):
                raise ValueError(ERROR_PIXELS)
            regions = saved_ocr(path)
            if regions:
                validate_ocr_regions(regions, after.size)
                text, _ = located_words(regions)
                scan_image_text(text, (), local_ner)
    return len(source)


def _verify_source_regions(
    regions: tuple[OcrRegion, ...], evidence: PixelFrame, local_ner: NerAdapter
) -> None:
    text, words = located_words(regions)
    clinical = protected_clinical_ranges(text)
    covered = []
    for span, box in words:
        if any(span.start < item.end and item.start < span.end for item in clinical):
            if any(intersects(box, mask.box) for mask in evidence.masks):
                raise ValueError(ERROR_CLINICAL_CHANGED)
        if any(
            mask.box[0] <= box[0]
            and mask.box[1] <= box[1]
            and box[2] <= mask.box[2]
            and box[3] <= mask.box[3]
            for mask in evidence.masks
        ):
            covered.append(span)
    scan_image_text(text, tuple(covered), local_ner)
