"""Load one model phase at a time, with separate detection and verification NER."""

import gc
from pathlib import Path

from redactor.inference.model_loader import load_local_ner_adapters
from redactor.inference.ocr_loader import load_local_ocr
from redactor.schemas.configuration import LocalSettings, ResourceSettings
from redactor.schemas.entities import NerAdapter, NerBatchAdapter, TextEntity
from redactor.schemas.ocr import OcrAdapter, OcrRegion
from redactor.utils.constants import NER_SPACY
from redactor.utils.errors import ERROR_LOCAL_UNAVAILABLE


def runtime_adapters(
    settings: LocalSettings, resources: ResourceSettings
) -> tuple[NerAdapter, OcrAdapter, NerAdapter]:
    ner, ocr, verifier, _ = runtime_model_adapters(settings, resources)
    return ner, ocr, verifier


def runtime_model_adapters(
    settings: LocalSettings, resources: ResourceSettings
) -> tuple[NerAdapter, OcrAdapter, NerAdapter, NerBatchAdapter]:
    ner: NerAdapter | None = None
    ner_batch: NerBatchAdapter | None = None
    active_settings: LocalSettings | None = None
    ocr: OcrAdapter | None = None
    verification_settings = settings.model_copy(
        update={"ner": NER_SPACY, "ner_directory": None}
    )

    def select_ner(
        selected: LocalSettings,
    ) -> tuple[NerAdapter, NerBatchAdapter | None]:
        nonlocal ner, ner_batch, active_settings, ocr
        if ocr is not None or active_settings != selected:
            ner, ner_batch, ocr = None, None, None
            gc.collect()
        if ner is None:
            ner, ner_batch = load_local_ner_adapters(selected)
            active_settings = selected
        return ner, ner_batch

    def recognize_text(text: str) -> tuple[TextEntity, ...]:
        recognize, _ = select_ner(settings)
        return recognize(text)

    def verify_text(text: str) -> tuple[TextEntity, ...]:
        recognize, _ = select_ner(verification_settings)
        return recognize(text)

    def verify_batch(texts: tuple[str, ...]) -> tuple[tuple[TextEntity, ...], ...]:
        if not texts:
            return ()
        _, recognize = select_ner(verification_settings)
        if recognize is None:
            raise ValueError(ERROR_LOCAL_UNAVAILABLE)
        return recognize(texts)

    def recognize_image(path: Path) -> tuple[OcrRegion, ...]:
        nonlocal ner, ner_batch, active_settings, ocr
        if ner is not None:
            ner, ner_batch, active_settings = None, None, None
            gc.collect()
        if ocr is None:
            ocr = load_local_ocr(settings, resources, word_boxes=True)
        return ocr(path)

    return recognize_text, recognize_image, verify_text, verify_batch


def local_adapters(
    settings: LocalSettings, resources: ResourceSettings
) -> tuple[NerAdapter, OcrAdapter]:
    """Expose the same detector/OCR pair to focused adapter integrations."""
    ner, ocr, _ = runtime_adapters(settings, resources)
    return ner, ocr
