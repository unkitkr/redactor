"""Load NER and OCR on demand, releasing the other heavyweight model first."""

import gc
from pathlib import Path

from redactor.inference.model_loader import load_local_ner
from redactor.inference.ocr_loader import load_local_ocr
from redactor.schemas.configuration import LocalSettings, ResourceSettings
from redactor.schemas.entities import NerAdapter, TextEntity
from redactor.schemas.ocr import OcrAdapter, OcrRegion


def local_adapters(
    settings: LocalSettings, resources: ResourceSettings
) -> tuple[NerAdapter, OcrAdapter]:
    ner: NerAdapter | None = None
    ocr: OcrAdapter | None = None

    def recognize_text(text: str) -> tuple[TextEntity, ...]:
        nonlocal ner, ocr
        if ocr is not None:
            ocr = None
            gc.collect()
        if ner is None:
            ner = load_local_ner(settings)
        return ner(text)

    def recognize_image(path: Path) -> tuple[OcrRegion, ...]:
        nonlocal ner, ocr
        if ner is not None:
            ner = None
            gc.collect()
        if ocr is None:
            ocr = load_local_ocr(settings, resources, word_boxes=True)
        return ocr(path)

    return recognize_text, recognize_image
