"""Exercise installed model weights, bounded caching and invalid model evidence."""

from pathlib import Path

import pytest

from redactor.inference.cache import cache_ner
from redactor.inference.evidence import validate_entity_evidence
from redactor.inference.ner import load_local_ner
from redactor.schemas.configuration import LocalSettings
from redactor.schemas.entities import TextEntities, TextEntity
from redactor.utils.errors import (
    ERROR_ENTITY_EVIDENCE,
    ERROR_LOCAL_INPUT,
    ERROR_LOCAL_UNAVAILABLE,
)


def test_installed_ner_returns_grounded_entities_and_bounds_working_state(
    tmp_path: Path,
) -> None:
    settings = LocalSettings(ner_max_characters=200)
    recognize = load_local_ner(settings)
    text = "John Smith lives in London."
    entities = recognize(text)
    assert ("John Smith", "person") in {
        (entity.text, entity.entity_type) for entity in entities
    }
    assert all(text[entity.start : entity.end] == entity.text for entity in entities)
    assert recognize(text) == entities
    assert recognize("") == ()
    # Objects returned from an earlier memory zone remain plain, usable values.
    for number in range(20):
        recognize(f"John Smith reviewed synthetic record {number}.")
    assert entities[0].text == "John Smith"
    with pytest.raises(ValueError, match=ERROR_LOCAL_INPUT):
        recognize("x" * 201)
    with pytest.raises(ValueError, match=ERROR_LOCAL_UNAVAILABLE):
        load_local_ner(LocalSettings(ner_directory=tmp_path / "missing-model"))

    calls = 0

    def counted_backend(value: str) -> tuple[TextEntity, ...]:
        nonlocal calls
        calls += 1
        return recognize(value)

    cached = cache_ner(counted_backend, maximum_entries=1, maximum_text_characters=30)
    cached(text)
    cached(text)
    assert calls == 1
    cached("Alice Jones lives in Paris.")
    cached(text)
    assert calls == 3  # The first input was evicted, rather than growing the cache.
    cached("This complete input exceeds the cache threshold.")
    cached("This complete input exceeds the cache threshold.")
    assert calls == 5
    invalid = TextEntities(
        entities=(TextEntity(start=0, end=10, text="Jane Smith", entity_type="person"),)
    )
    with pytest.raises(ValueError, match=ERROR_ENTITY_EVIDENCE):
        validate_entity_evidence(text, invalid)
    overlapping = TextEntities(entities=(entities[0], entities[0]))
    with pytest.raises(ValueError, match=ERROR_ENTITY_EVIDENCE):
        validate_entity_evidence(text, overlapping)
