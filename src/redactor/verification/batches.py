"""Bound verifier inference without changing the text or its evidence checks."""

from collections import OrderedDict
from collections.abc import Iterable, Iterator

from redactor.schemas.entities import NerAdapter, NerBatchAdapter, TextEntity
from redactor.schemas.tabular import CsvRowPair
from redactor.schemas.verification import ResidualCheck
from redactor.utils.constants import (
    SPACY_BATCH_SIZE,
    VERIFICATION_BATCH_BYTES,
    VERIFICATION_BATCH_CHARACTERS,
    VERIFICATION_BATCH_RECORDS,
)
from redactor.utils.errors import ERROR_ENTITY_EVIDENCE


def row_batches(rows: Iterable[CsvRowPair]) -> Iterator[tuple[CsvRowPair, ...]]:
    """A single large record remains bounded by the independent CSV reader."""
    batch: list[CsvRowPair] = []
    characters = 0
    for pair in rows:
        # Delimiters also consume space: wide empty rows must not evade the bound.
        size = sum(len(row) + sum(len(value) for value in row) for row in pair)
        if batch and (
            len(batch) >= VERIFICATION_BATCH_RECORDS
            or (characters + size) * 4 > VERIFICATION_BATCH_BYTES
        ):
            yield tuple(batch)
            batch.clear()
            characters = 0
        batch.append(pair)
        characters += size
    if batch:
        yield tuple(batch)


def batch_verifier(
    checks: list[ResidualCheck],
    local_ner: NerAdapter,
    batch_ner: NerBatchAdapter | None,
    cache: OrderedDict[str, tuple[TextEntity, ...]],
    *,
    maximum_entries: int,
    maximum_text_characters: int,
) -> NerAdapter:
    """Cache model observations, never context-dependent verification verdicts.

    The returned recognizer raises on unseen text: callers may only pass the
    statistical texts collected for this same batch.
    """
    texts = dict.fromkeys(check.statistical_text for check in checks)
    observations: dict[str, tuple[TextEntity, ...]] = {}
    pending: list[str] = []
    characters = 0

    def remember(text: str, entities: tuple[TextEntity, ...]) -> None:
        observations[text] = entities
        if len(text) <= maximum_text_characters:
            cache[text] = entities
            cache.move_to_end(text)
            while len(cache) > maximum_entries:
                cache.popitem(last=False)

    def collect() -> None:
        results = (
            batch_ner(tuple(pending))
            if batch_ner is not None
            else tuple(local_ner(text) for text in pending)
        )
        if len(results) != len(pending):
            raise ValueError(ERROR_ENTITY_EVIDENCE)
        for text, entities in zip(pending, results, strict=True):
            remember(text, entities)
        pending.clear()

    for text in texts:
        if text in cache:
            observations[text] = cache[text]
            cache.move_to_end(text)
            continue
        if pending and (
            len(pending) >= SPACY_BATCH_SIZE
            or characters + len(text) > VERIFICATION_BATCH_CHARACTERS
        ):
            collect()
            characters = 0
        if len(text) > VERIFICATION_BATCH_CHARACTERS:
            remember(text, local_ner(text))
        else:
            pending.append(text)
            characters += len(text)
    if pending:
        collect()

    def recognize(text: str) -> tuple[TextEntity, ...]:
        return observations[text]

    return recognize
