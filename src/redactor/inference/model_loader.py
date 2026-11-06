"""Select installed models and apply the same bounds and evidence contract."""

from redactor.inference.cache import cache_ner
from redactor.inference.evidence import validate_entity_evidence
from redactor.inference.ocr_loader import load_local_ocr as load_local_ocr
from redactor.schemas.configuration import LocalSettings
from redactor.schemas.entities import NerAdapter, TextEntities, TextEntity
from redactor.utils.constants import NER_GLINER, NER_SPACY
from redactor.utils.errors import (
    ERROR_ENTITY_EVIDENCE,
    ERROR_LOCAL_INFERENCE,
    ERROR_LOCAL_INPUT,
    ERROR_LOCAL_UNAVAILABLE,
)


def load_local_ner(settings: LocalSettings) -> NerAdapter:
    """Load once per inference worker, without downloads or a silent model switch."""
    try:
        if settings.ner == NER_SPACY:
            from redactor.inference.adapters.spacy import load_spacy

            adapter = load_spacy(settings)
        elif settings.ner == NER_GLINER and settings.ner_directory is not None:
            from redactor.inference.adapters.gliner import load_gliner

            adapter = load_gliner(settings.ner_directory)
        else:
            raise ValueError(ERROR_LOCAL_UNAVAILABLE)
    except Exception:
        # Library exceptions can contain file paths or model data.
        raise ValueError(ERROR_LOCAL_UNAVAILABLE) from None
    return prepare_ner(adapter, settings)


def prepare_ner(adapter: NerAdapter, settings: LocalSettings) -> NerAdapter:
    """Compose validation before caching, also for experimental local adapters."""

    def recognize(text: str) -> tuple[TextEntity, ...]:
        if len(text) > settings.ner_max_characters:
            raise ValueError(ERROR_LOCAL_INPUT)
        try:
            entities = adapter(text)
        except Exception as error:
            for code in (
                ERROR_LOCAL_INPUT,
                ERROR_LOCAL_UNAVAILABLE,
                ERROR_ENTITY_EVIDENCE,
            ):
                if error.args == (code,):
                    raise ValueError(code) from None
            raise ValueError(ERROR_LOCAL_INFERENCE) from None
        try:
            return validate_entity_evidence(text, TextEntities(entities=entities))
        except Exception:
            raise ValueError(ERROR_ENTITY_EVIDENCE) from None

    return cache_ner(
        recognize,
        maximum_entries=settings.ner_cache_entries,
        maximum_text_characters=settings.ner_cache_characters,
    )
