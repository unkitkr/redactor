"""Bound image inputs and validate OCR observations independently of the engine."""

import io
import math
import warnings
from pathlib import Path

from PIL import Image

from redactor.schemas.ocr import OcrRegion
from redactor.utils.constants import (
    OCR_IMAGE_FORMATS,
    OCR_MAXIMUM_ASPECT_RATIO,
    OCR_MAXIMUM_REGION_CHARACTERS,
    OCR_MAXIMUM_REGIONS,
)
from redactor.utils.errors import ERROR_LOCAL_INFERENCE, ERROR_LOCAL_INPUT


def read_ocr_image(
    path: Path, *, maximum_bytes: int, maximum_pixels: int
) -> tuple[bytes, tuple[int, int], str]:
    """Read bounded bytes and inspect dimensions before any pixel decompression."""
    try:
        if not path.is_file() or not 0 < path.stat().st_size <= maximum_bytes:
            raise ValueError(ERROR_LOCAL_INPUT)
        with path.open("rb") as stream:
            content = stream.read(maximum_bytes + 1)
        if not content or len(content) > maximum_bytes:
            raise ValueError(ERROR_LOCAL_INPUT)
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(content)) as image:
                width, height = image.size
                image_format = image.format
                if (
                    width <= 0
                    or height <= 0
                    or width * height > maximum_pixels
                    or max(width, height)
                    > min(width, height) * OCR_MAXIMUM_ASPECT_RATIO
                    or image_format not in OCR_IMAGE_FORMATS
                    or getattr(image, "n_frames", 1) != 1
                ):
                    raise ValueError(ERROR_LOCAL_INPUT)
                image.verify()
        assert image_format is not None
        return content, (width, height), image_format
    except Exception:
        raise ValueError(ERROR_LOCAL_INPUT) from None


def validate_ocr_regions(
    regions: tuple[OcrRegion, ...], size: tuple[int, int]
) -> tuple[OcrRegion, ...]:
    """Empty OCR is unknown coverage, not evidence that an image contains no text."""
    if not isinstance(regions, tuple) or not 0 < len(regions) <= OCR_MAXIMUM_REGIONS:
        raise ValueError(ERROR_LOCAL_INFERENCE)
    width, height = size
    for region in regions:
        if (
            not isinstance(region, OcrRegion)
            or not region.text.strip()
            or len(region.text) > OCR_MAXIMUM_REGION_CHARACTERS
            or not all(math.isfinite(value) for value in region.box)
        ):
            raise ValueError(ERROR_LOCAL_INFERENCE)
        left, top, right, bottom = region.box
        if not (0 <= left < right <= width and 0 <= top < bottom <= height):
            raise ValueError(ERROR_LOCAL_INFERENCE)
    return regions
