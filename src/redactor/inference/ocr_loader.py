"""Compose local OCR engines with common input bounds and evidence validation."""

import hashlib
from pathlib import Path

from redactor.inference.ocr_evidence import read_ocr_image, validate_ocr_regions
from redactor.schemas.configuration import LocalSettings, ResourceSettings
from redactor.schemas.ocr import OcrAdapter, OcrRegion
from redactor.utils.constants import (
    OCR_PPOCR,
    OCR_PPOCR_DIRECTORY,
    OCR_TESSDATA_DIRECTORY,
    OCR_TESSERACT,
)
from redactor.utils.errors import (
    ERROR_LOCAL_INFERENCE,
    ERROR_LOCAL_INPUT,
    ERROR_LOCAL_UNAVAILABLE,
)


def load_local_ocr(
    settings: LocalSettings, resources: ResourceSettings, *, word_boxes: bool = False
) -> OcrAdapter:
    try:
        if settings.ocr == OCR_TESSERACT:
            from redactor.inference.adapters.tesseract import load_tesseract

            directory = settings.ocr_directory or (
                settings.model_directory / OCR_TESSDATA_DIRECTORY
            )
            adapter = load_tesseract(
                directory, settings.ocr_language, word_boxes=word_boxes
            )
        elif settings.ocr == OCR_PPOCR:
            from redactor.inference.adapters.ppocr import load_ppocr

            directory = settings.ocr_directory or (
                settings.model_directory / OCR_PPOCR_DIRECTORY
            )
            adapter = load_ppocr(
                directory, settings.ocr_language, word_boxes=word_boxes
            )
        else:
            raise ValueError(ERROR_LOCAL_UNAVAILABLE)
    except Exception:
        raise ValueError(ERROR_LOCAL_UNAVAILABLE) from None
    return bounded_ocr(adapter, resources)


def bounded_ocr(adapter: OcrAdapter, resources: ResourceSettings) -> OcrAdapter:
    def recognize(path: Path) -> tuple[OcrRegion, ...]:
        content, size, _ = read_ocr_image(
            path,
            maximum_bytes=resources.max_native_file_bytes,
            maximum_pixels=resources.max_image_pixels,
        )
        digest = hashlib.sha256(content).digest()
        del content
        try:
            regions = validate_ocr_regions(adapter(path), size)
        except Exception:
            raise ValueError(ERROR_LOCAL_INFERENCE) from None
        current, _, _ = read_ocr_image(
            path,
            maximum_bytes=resources.max_native_file_bytes,
            maximum_pixels=resources.max_image_pixels,
        )
        if hashlib.sha256(current).digest() != digest:
            raise ValueError(ERROR_LOCAL_INPUT)
        return regions

    return recognize
