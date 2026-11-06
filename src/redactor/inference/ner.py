"""Load a local CPU model once and expose it as a bounded text-to-spans function."""

from typing import TYPE_CHECKING

from redactor.inference.cache import cache_ner
from redactor.inference.evidence import validate_entity_evidence
from redactor.schemas.configuration import LocalSettings
from redactor.schemas.entities import EntityType, NerAdapter, TextEntities, TextEntity
from redactor.utils.constants import (
    NER_SPACY,
    SPACY_ENTITY_TYPES,
    SPACY_EXCLUDED_COMPONENTS,
    SPACY_NER_COMPONENT,
)
from redactor.utils.errors import (
    ERROR_LOCAL_INFERENCE,
    ERROR_LOCAL_INPUT,
    ERROR_LOCAL_UNAVAILABLE,
)

if TYPE_CHECKING:
    from spacy.language import Language


def load_local_ner(settings: LocalSettings) -> NerAdapter:
    """Only inference workers call this; no import-time model or network activity."""
    if settings.ner != NER_SPACY:
        raise ValueError(ERROR_LOCAL_UNAVAILABLE)
    adapter = load_spacy_ner(settings)
    return cache_ner(
        adapter,
        maximum_entries=settings.ner_cache_entries,
        maximum_text_characters=settings.ner_cache_characters,
    )


def load_spacy_ner(settings: LocalSettings) -> NerAdapter:
    try:
        import spacy

        nlp = spacy.load(
            settings.ner_directory or settings.spacy_model,
            exclude=SPACY_EXCLUDED_COMPONENTS,
        )
    except (ImportError, OSError, ValueError):
        raise ValueError(ERROR_LOCAL_UNAVAILABLE) from None
    if SPACY_NER_COMPONENT not in nlp.pipe_names:
        raise ValueError(ERROR_LOCAL_UNAVAILABLE)
    entity_types: dict[str, EntityType] = dict(SPACY_ENTITY_TYPES)

    def recognize(text: str) -> tuple[TextEntity, ...]:
        if len(text) > settings.ner_max_characters:
            raise ValueError(ERROR_LOCAL_INPUT)
        try:
            with nlp.memory_zone():
                result = _recognize(nlp, text, entity_types)
        except Exception:
            # Third-party errors can include input text. Only a safe code escapes.
            raise ValueError(ERROR_LOCAL_INFERENCE) from None
        return validate_entity_evidence(text, result)

    return recognize


def _recognize(
    nlp: "Language", text: str, entity_types: dict[str, EntityType]
) -> TextEntities:
    """Copy plain values before the memory zone releases spaCy's vocabulary."""
    document = nlp(text)
    return TextEntities(
        entities=tuple(
            TextEntity(
                start=entity.start_char,
                end=entity.end_char,
                text=entity.text,
                entity_type=entity_types[entity.label_],
            )
            for entity in document.ents
            if entity.label_ in entity_types
        )
    )
