"""Normalize every image frame and write fresh containers without source metadata."""

import hashlib
import io
from pathlib import Path

from PIL import Image, ImageDraw, ImageOps

from redactor.schemas.configuration import ResourceSettings
from redactor.schemas.pixels import PixelMask
from redactor.utils.constants import (
    PIXEL_IMAGE_MODES,
    PIXEL_JPEG_FORMAT,
    PIXEL_JPEG_QUALITY,
    PIXEL_MASK_COLOR,
    PIXEL_MAXIMUM_FRAMES,
    PIXEL_PNG_FORMAT,
    PIXEL_RGB_MODE,
    PIXEL_TIFF_COMPRESSION,
    PIXEL_TIFF_FORMAT,
)
from redactor.utils.errors import ERROR_COVERAGE, ERROR_RESOURCE_LIMIT, ERROR_STRUCTURE


def read_image_frames(
    path: Path, resources: ResourceSettings
) -> tuple[Image.Image, ...]:
    frames: list[Image.Image] = []
    pixels = 0
    with Image.open(path) as source:
        for number in range(getattr(source, "n_frames", 1)):
            if number >= PIXEL_MAXIMUM_FRAMES:
                raise ValueError(ERROR_RESOURCE_LIMIT)
            source.seek(number)
            pixels += source.width * source.height
            if pixels > resources.max_image_pixels:
                raise ValueError(ERROR_RESOURCE_LIMIT)
            if source.mode not in PIXEL_IMAGE_MODES or "transparency" in source.info:
                raise ValueError(ERROR_COVERAGE)
            oriented = ImageOps.exif_transpose(source)
            # A fresh image discards EXIF, XMP, thumbnails and arbitrary tags.
            frame = Image.frombytes(
                PIXEL_RGB_MODE,
                oriented.size,
                oriented.convert(PIXEL_RGB_MODE).tobytes(),
            )
            frames.append(frame)
    if not frames:
        raise ValueError(ERROR_STRUCTURE)
    return tuple(frames)


def pixel_digest(image: Image.Image) -> str:
    return hashlib.sha256(image.tobytes()).hexdigest()


def mask_image(image: Image.Image, masks: tuple[PixelMask, ...]) -> Image.Image:
    result = image.copy()
    draw = ImageDraw.Draw(result)
    for mask in masks:
        left, top, right, bottom = mask.box
        if not (0 <= left < right <= image.width and 0 <= top < bottom <= image.height):
            raise ValueError(ERROR_COVERAGE)
        draw.rectangle((left, top, right - 1, bottom - 1), fill=PIXEL_MASK_COLOR)
    return result


def encode_image_frames(frames: tuple[Image.Image, ...], image_format: str) -> bytes:
    if not frames or (image_format != PIXEL_TIFF_FORMAT and len(frames) != 1):
        raise ValueError(ERROR_STRUCTURE)
    target = io.BytesIO()
    if image_format == PIXEL_JPEG_FORMAT:
        frames[0].save(
            target, format=image_format, quality=PIXEL_JPEG_QUALITY, subsampling=0
        )
    elif image_format == PIXEL_TIFF_FORMAT:
        frames[0].save(
            target,
            format=image_format,
            save_all=True,
            append_images=frames[1:],
            compression=PIXEL_TIFF_COMPRESSION,
        )
    elif image_format == PIXEL_PNG_FORMAT:
        frames[0].save(target, format=image_format)
    else:
        raise ValueError(ERROR_STRUCTURE)
    return target.getvalue()
