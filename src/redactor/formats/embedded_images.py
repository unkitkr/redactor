"""Use the same bounded pixel path inside native document containers."""

import io
from pathlib import Path
from tempfile import TemporaryDirectory

from PIL import Image

from redactor.formats.images import (
    encode_image_frames,
    mask_image,
    pixel_digest,
    read_image_frames,
)
from redactor.inference.images import analyze_image_content
from redactor.schemas.configuration import PipelineSettings
from redactor.schemas.entities import NerAdapter
from redactor.schemas.native import NativeImage
from redactor.schemas.ocr import OcrAdapter
from redactor.schemas.pixels import EmbeddedImageEvidence
from redactor.utils.constants import PIXEL_TEMPORARY_FILENAME
from redactor.utils.errors import ERROR_COVERAGE, ERROR_RESOURCE_LIMIT


def embedded_pixel_count(image: NativeImage, maximum: int) -> int:
    """Reject an aggregate image budget before model loading or pixel decoding."""
    pixels = 0
    with Image.open(io.BytesIO(image.content)) as source:
        for number in range(getattr(source, "n_frames", 1)):
            source.seek(number)
            pixels += source.width * source.height
            if pixels > maximum:
                raise ValueError(ERROR_RESOURCE_LIMIT)
    return pixels


def analyze_embedded_image(
    image: NativeImage,
    settings: PipelineSettings,
    detector: NerAdapter,
    ocr: OcrAdapter,
    *,
    patient_name: str = "",
    provider_name: str = "",
) -> EmbeddedImageEvidence:
    with TemporaryDirectory() as temporary:
        path = Path(temporary) / PIXEL_TEMPORARY_FILENAME
        path.write_bytes(image.content)
        with Image.open(path) as source:
            image_format = source.format
        if image_format is None:
            raise ValueError(ERROR_COVERAGE)
        frames, counts = analyze_image_content(
            path,
            settings,
            detector,
            ocr,
            patient_name=patient_name,
            provider_name=provider_name,
        )
    return EmbeddedImageEvidence(
        location=image.location, image_format=image_format, frames=frames, counts=counts
    )


def rewrite_embedded_images(
    images: tuple[NativeImage, ...],
    evidence: tuple[EmbeddedImageEvidence, ...],
    settings: PipelineSettings,
) -> dict[tuple[str, ...], bytes]:
    locations = tuple(image.location for image in images)
    if any(not location for location in locations) or len(set(locations)) != len(
        locations
    ):
        raise ValueError(ERROR_COVERAGE)
    if locations != tuple(e.location for e in evidence):
        raise ValueError(ERROR_COVERAGE)
    replacements: dict[tuple[str, ...], bytes] = {}
    with TemporaryDirectory() as temporary:
        path = Path(temporary) / PIXEL_TEMPORARY_FILENAME
        for image, assessment in zip(images, evidence, strict=True):
            path.write_bytes(image.content)
            frames = read_image_frames(path, settings.resources)
            if len(frames) != len(assessment.frames):
                raise ValueError(ERROR_COVERAGE)
            if any(
                frame.size != (item.width, item.height)
                or pixel_digest(frame) != item.sha256
                for frame, item in zip(frames, assessment.frames, strict=True)
            ):
                raise ValueError(ERROR_COVERAGE)
            rewritten = tuple(
                mask_image(frame, item.masks)
                for frame, item in zip(frames, assessment.frames, strict=True)
            )
            replacements[image.location] = encode_image_frames(
                rewritten, assessment.image_format
            )
    return replacements
