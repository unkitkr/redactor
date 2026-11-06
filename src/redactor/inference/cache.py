"""Cache only small inference inputs, with a separate cache per worker instance."""

from functools import lru_cache

from redactor.schemas.entities import NerAdapter, TextEntity


def cache_ner(
    adapter: NerAdapter, *, maximum_entries: int, maximum_text_characters: int
) -> NerAdapter:
    """Long units still run fully but never occupy the small-text cache."""
    cached = lru_cache(maxsize=maximum_entries)(adapter)

    def recognize(text: str) -> tuple[TextEntity, ...]:
        if len(text) > maximum_text_characters:
            return adapter(text)
        return cached(text)

    return recognize
