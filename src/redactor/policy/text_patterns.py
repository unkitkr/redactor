"""Locate deterministic text evidence and protect explicit clinical expressions."""

import re

from redactor.policy.clinical_codes import snomed_ranges
from redactor.schemas.redaction import TextRange
from redactor.utils.constants import (
    AGE_EXPLICIT_PATTERN,
    AGE_GROUP_MINIMUM,
    AGE_WORD_PATTERN,
    AGE_YEARS_PATTERN,
    CLINICAL_NEGATION_PREFIX_PATTERN,
    CLINICAL_RANGE_GAP_PATTERN,
    TEXT_CLINICAL_PATTERNS,
)


def clinical_ranges(text: str) -> tuple[TextRange, ...]:
    ranges = tuple(
        TextRange(start=match.start(), end=match.end())
        for pattern in TEXT_CLINICAL_PATTERNS
        for match in re.finditer(pattern, text)
    ) + snomed_ranges(text)
    expanded: list[TextRange] = []
    for span in ranges:
        negation = re.search(CLINICAL_NEGATION_PREFIX_PATTERN, text[: span.start])
        expanded.append(
            TextRange(start=negation.start() if negation else span.start, end=span.end)
        )
    merged: list[TextRange] = []
    for span in sorted(expanded, key=lambda item: (item.start, item.end)):
        if merged and (
            span.start <= merged[-1].end
            or re.fullmatch(
                CLINICAL_RANGE_GAP_PATTERN, text[merged[-1].end : span.start]
            )
            is not None
        ):
            merged[-1] = TextRange(
                start=merged[-1].start, end=max(merged[-1].end, span.end)
            )
        else:
            merged.append(span)
    return tuple(merged)


def age_mentions(text: str) -> tuple[tuple[TextRange, TextRange, int], ...]:
    return tuple(
        (
            TextRange(start=match.start(), end=match.end()),
            TextRange(start=match.start("age"), end=match.end("age")),
            int(match["age"]) if match["age"].isdigit() else AGE_GROUP_MINIMUM,
        )
        for pattern in (AGE_EXPLICIT_PATTERN, AGE_YEARS_PATTERN, AGE_WORD_PATTERN)
        for match in re.finditer(pattern, text)
    )
