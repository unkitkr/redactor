"""Keep spaCy's pipeline and vocabulary lifetime behind a plain NER function."""

from typing import TYPE_CHECKING

from redactor.schemas.configuration import LocalSettings
from redactor.schemas.entities import (
    EntityType,
    NerAdapter,
    NerBatchAdapter,
    TextEntity,
)
from redactor.utils.constants import (
    SPACY_BATCH_SIZE,
    SPACY_ENTITY_TYPES,
    SPACY_EXCLUDED_COMPONENTS,
    SPACY_NER_COMPONENT,
)
from redactor.utils.errors import ERROR_LOCAL_UNAVAILABLE

if TYPE_CHECKING:
    from spacy.tokens import Doc


def load_spacy(settings: LocalSettings) -> NerAdapter:
    recognize, _ = load_spacy_adapters(settings)
    return recognize


def load_spacy_adapters(settings: LocalSettings) -> tuple[NerAdapter, NerBatchAdapter]:
    """Share one model across single inputs and bounded in-process batches."""
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
            return _entities(nlp(text), entity_types)

    def recognize_many(texts: tuple[str, ...]) -> tuple[tuple[TextEntity, ...], ...]:
        results: list[tuple[TextEntity, ...]] = []
        for start in range(0, len(texts), SPACY_BATCH_SIZE):
            with nlp.memory_zone():
                results.extend(
                    _entities(document, entity_types)
                    for document in nlp.pipe(
                        texts[start : start + SPACY_BATCH_SIZE],
                        batch_size=SPACY_BATCH_SIZE,
                        n_process=1,
                    )
                )
        return tuple(results)

    return recognize, recognize_many


def _entities(
    document: "Doc", entity_types: dict[str, EntityType]
) -> tuple[TextEntity, ...]:
    """Copy plain values before the memory zone releases spaCy's vocabulary."""
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
