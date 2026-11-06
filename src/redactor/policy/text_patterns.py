"""Locate deterministic text evidence and protect explicit clinical expressions."""

import re

from redactor.schemas.redaction import TextRange
from redactor.utils.constants import (
    AGE_EXPLICIT_PATTERN,
    AGE_GROUP_MINIMUM,
    AGE_WORD_PATTERN,
    AGE_YEARS_PATTERN,
    TEXT_CLINICAL_PATTERNS,
)


def clinical_ranges(text: str) -> tuple[TextRange, ...]:
    return tuple(
        TextRange(start=match.start(), end=match.end())
        for pattern in TEXT_CLINICAL_PATTERNS
        for match in re.finditer(pattern, text)
    )


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
