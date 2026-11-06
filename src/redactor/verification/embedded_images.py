"""Reopen extracted original and saved image members through the pixel verifier."""

from pathlib import Path
from tempfile import TemporaryDirectory

from redactor.schemas.configuration import PipelineSettings
from redactor.schemas.entities import NerAdapter
from redactor.schemas.native import NativeDocument
from redactor.schemas.pixels import EmbeddedImageEvidence
from redactor.utils.constants import PIXEL_TEMPORARY_FILENAME
from redactor.utils.errors import ERROR_COVERAGE
from redactor.verification.images import verify_image_content


def verify_embedded_images(
    original: NativeDocument,
    saved: NativeDocument,
    evidence: tuple[EmbeddedImageEvidence, ...],
    settings: PipelineSettings,
    local_ner: NerAdapter,
) -> int:
    locations = tuple(image.location for image in original.images)
    if any(not location for location in locations) or len(set(locations)) != len(
        locations
    ):
        raise ValueError(ERROR_COVERAGE)
    if locations != tuple(
        image.location for image in saved.images
    ) or locations != tuple(item.location for item in evidence):
        raise ValueError(ERROR_COVERAGE)
    frames = 0
    with TemporaryDirectory() as first, TemporaryDirectory() as second:
        source_path = Path(first) / PIXEL_TEMPORARY_FILENAME
        saved_path = Path(second) / PIXEL_TEMPORARY_FILENAME
        for source, output, assessment in zip(
            original.images, saved.images, evidence, strict=True
        ):
            source_path.write_bytes(source.content)
            saved_path.write_bytes(output.content)
            frames += verify_image_content(
                source_path,
                saved_path,
                assessment.frames,
                assessment.image_format,
                settings,
                local_ner,
            )
    return frames
