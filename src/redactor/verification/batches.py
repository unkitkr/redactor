"""Bound verifier inference without changing the text or its evidence checks."""

from collections.abc import Iterable, Iterator
from unicodedata import normalize

from redactor.schemas.entities import NerAdapter, NerBatchAdapter, TextEntity
from redactor.schemas.redaction import ColumnPolicy
from redactor.schemas.tabular import CsvRowPair
from redactor.utils.constants import (
    FIELD_TEXT,
    SPACY_BATCH_SIZE,
    UNICODE_NORMAL_FORM,
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
    rows: tuple[CsvRowPair, ...],
    policies: tuple[ColumnPolicy, ...],
    local_ner: NerAdapter,
    batch_ner: NerBatchAdapter | None,
) -> NerAdapter:
    """Prefetch exact source/output observations, including normalization views."""
    if batch_ner is None:
        return local_ner
    texts = dict.fromkeys(
        view
        for pair in rows
        for row in pair
        for column in policies
        if column.kind == FIELD_TEXT
        for value in (row[column.index],)
        for view in (value, normalize(UNICODE_NORMAL_FORM, value))
    )
    observations: dict[str, tuple[TextEntity, ...]] = {}
    pending: list[str] = []
    characters = 0

    def collect() -> None:
        results = batch_ner(tuple(pending))
        if len(results) != len(pending):
            raise ValueError(ERROR_ENTITY_EVIDENCE)
        observations.update(zip(pending, results, strict=True))
        pending.clear()

    for text in texts:
        if pending and (
            len(pending) >= SPACY_BATCH_SIZE
            or characters + len(text) > VERIFICATION_BATCH_CHARACTERS
        ):
            collect()
            characters = 0
        if len(text) > VERIFICATION_BATCH_CHARACTERS:
            observations[text] = local_ner(text)
        else:
            pending.append(text)
            characters += len(text)
    if pending:
        collect()

    def recognize(text: str) -> tuple[TextEntity, ...]:
        if text in observations:
            return observations[text]
        return local_ner(text)

    return recognize
