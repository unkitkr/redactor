"""Load one model phase at a time, with separate detection and verification NER."""

import gc
from pathlib import Path

from redactor.inference.model_loader import load_local_ner
from redactor.inference.ocr_loader import load_local_ocr
from redactor.schemas.configuration import LocalSettings, ResourceSettings
from redactor.schemas.entities import NerAdapter, TextEntity
from redactor.schemas.ocr import OcrAdapter, OcrRegion
from redactor.utils.constants import NER_SPACY


def runtime_adapters(
    settings: LocalSettings, resources: ResourceSettings
) -> tuple[NerAdapter, OcrAdapter, NerAdapter]:
    ner: NerAdapter | None = None
    ner_backend: str | None = None
    ocr: OcrAdapter | None = None
    verification_settings = settings.model_copy(
        update={"ner": NER_SPACY, "ner_directory": None}
    )

    def recognize(text: str, selected: LocalSettings) -> tuple[TextEntity, ...]:
        nonlocal ner, ner_backend, ocr
        if ocr is not None or ner_backend != selected.ner:
            ner, ocr = None, None
            gc.collect()
        if ner is None:
            ner = load_local_ner(selected)
            ner_backend = selected.ner
        return ner(text)

    def recognize_text(text: str) -> tuple[TextEntity, ...]:
        return recognize(text, settings)

    def verify_text(text: str) -> tuple[TextEntity, ...]:
        return recognize(text, verification_settings)

    def recognize_image(path: Path) -> tuple[OcrRegion, ...]:
        nonlocal ner, ner_backend, ocr
        if ner is not None:
            ner, ner_backend = None, None
            gc.collect()
        if ocr is None:
            ocr = load_local_ocr(settings, resources, word_boxes=True)
        return ocr(path)

    return recognize_text, recognize_image, verify_text


def local_adapters(
    settings: LocalSettings, resources: ResourceSettings
) -> tuple[NerAdapter, OcrAdapter]:
    """Expose the same detector/OCR pair to focused adapter integrations."""
    ner, ocr, _ = runtime_adapters(settings, resources)
    return ner, ocr
