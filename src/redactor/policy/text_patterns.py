"""Locate deterministic text evidence and protect explicit clinical expressions."""

import re
from collections.abc import Callable

from redactor.policy.clinical_codes import snomed_ranges
from redactor.schemas.redaction import TextRange
from redactor.utils.constants import (
    AGE_EXPLICIT_PATTERN,
    AGE_GROUP_MINIMUM,
    AGE_WORD_PATTERN,
    AGE_YEARS_PATTERN,
    CLINICAL_NEGATION_PREFIX_PATTERN,
    CLINICAL_RANGE_GAP_PATTERN,
    ROLE_NARRATIVE_VERB_PATTERN,
    TEXT_CLINICAL_PATTERNS,
    TEXT_PROVIDER_PATTERN,
    TEXT_RELATIVE_PATTERN,
    VERIFIER_RELATIVE_TIME_PATTERN,
)


def clinical_ranges(text: str) -> tuple[TextRange, ...]:
    ranges = (
        tuple(
            TextRange(start=match.start(), end=match.end())
            for pattern in (*TEXT_CLINICAL_PATTERNS, VERIFIER_RELATIVE_TIME_PATTERN)
            for match in re.finditer(pattern, text)
        )
        + snomed_ranges(text)
        + narrative_predicates(text)
    )
    return _merge_clinical_ranges(text, ranges)


def make_clinical_matcher() -> Callable[[str], tuple[TextRange, ...]]:
    """Compile the fixed clinical expressions once for one processing stage."""
    patterns = tuple(
        re.compile(pattern)
        for pattern in (*TEXT_CLINICAL_PATTERNS, VERIFIER_RELATIVE_TIME_PATTERN)
    )

    def locate(text: str) -> tuple[TextRange, ...]:
        ranges = (
            tuple(
                TextRange(start=match.start(), end=match.end())
                for pattern in patterns
                for match in pattern.finditer(text)
            )
            + snomed_ranges(text)
            + narrative_predicates(text)
        )
        return _merge_clinical_ranges(text, ranges)

    return locate


def _merge_clinical_ranges(
    text: str, ranges: tuple[TextRange, ...]
) -> tuple[TextRange, ...]:
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


def narrative_predicates(text: str) -> tuple[TextRange, ...]:
    """A grammatical action after an explicit person role is not a location.

    Only the verb is protected. Every part of the preceding name still requires
    its own transformation and independent residual check.
    """
    ranges: list[TextRange] = []
    for pattern in (TEXT_PROVIDER_PATTERN, TEXT_RELATIVE_PATTERN):
        for person in re.finditer(pattern, text):
            end = person.end("name")
            predicate = re.match(ROLE_NARRATIVE_VERB_PATTERN, text[end:])
            if predicate:
                start, stop = predicate.span("verb")
                ranges.append(TextRange(start=end + start, end=end + stop))
    return tuple(ranges)


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
