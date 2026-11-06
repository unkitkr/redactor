"""Keep spaCy's pipeline and vocabulary lifetime behind a plain NER function."""

from typing import TYPE_CHECKING

from redactor.schemas.configuration import LocalSettings
from redactor.schemas.entities import EntityType, NerAdapter, TextEntity
from redactor.utils.constants import (
    SPACY_ENTITY_TYPES,
    SPACY_EXCLUDED_COMPONENTS,
    SPACY_NER_COMPONENT,
)
from redactor.utils.errors import ERROR_LOCAL_UNAVAILABLE

if TYPE_CHECKING:
    from spacy.language import Language


def load_spacy(settings: LocalSettings) -> NerAdapter:
    import spacy

    nlp = spacy.load(
        settings.ner_directory or settings.spacy_model,
        exclude=SPACY_EXCLUDED_COMPONENTS,
    )
    if SPACY_NER_COMPONENT not in nlp.pipe_names:
        raise ValueError(ERROR_LOCAL_UNAVAILABLE)
    entity_types: dict[str, EntityType] = dict(SPACY_ENTITY_TYPES)

    def recognize(text: str) -> tuple[TextEntity, ...]:
        with nlp.memory_zone():
            return _recognize(nlp, text, entity_types)

    return recognize


def _recognize(
    nlp: "Language", text: str, entity_types: dict[str, EntityType]
) -> tuple[TextEntity, ...]:
    """Copy plain values before the memory zone releases spaCy's vocabulary."""
    document = nlp(text)
    return tuple(
        TextEntity(
            start=entity.start_char,
            end=entity.end_char,
            text=entity.text,
            entity_type=entity_types[entity.label_],
        )
        for entity in document.ents
        if entity.label_ in entity_types
    )
