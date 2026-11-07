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

_CLINICAL_PATTERNS = tuple(
    re.compile(pattern)
    for pattern in (*TEXT_CLINICAL_PATTERNS, VERIFIER_RELATIVE_TIME_PATTERN)
)
_NEGATION_PREFIX = re.compile(CLINICAL_NEGATION_PREFIX_PATTERN)
_RANGE_GAP = re.compile(CLINICAL_RANGE_GAP_PATTERN)
_PERSON_ROLE_PATTERNS = tuple(
    re.compile(pattern) for pattern in (TEXT_PROVIDER_PATTERN, TEXT_RELATIVE_PATTERN)
)
_ROLE_NARRATIVE_VERB = re.compile(ROLE_NARRATIVE_VERB_PATTERN)
_AGE_PATTERNS = tuple(
    re.compile(pattern)
    for pattern in (AGE_EXPLICIT_PATTERN, AGE_YEARS_PATTERN, AGE_WORD_PATTERN)
)


def clinical_ranges(text: str) -> tuple[TextRange, ...]:
    spans = (
        tuple(
            (match.start(), match.end())
            for pattern in _CLINICAL_PATTERNS
            for match in pattern.finditer(text)
        )
        + tuple((span.start, span.end) for span in snomed_ranges(text))
        + tuple((span.start, span.end) for span in narrative_predicates(text))
    )
    return tuple(
        TextRange(start=start, end=end)
        for start, end in _merge_clinical_ranges(text, spans)
    )


def make_clinical_matcher() -> Callable[[str], tuple[TextRange, ...]]:
    """Match the fixed clinical expressions through the shared compiled set."""

    def locate(text: str) -> tuple[TextRange, ...]:
        return clinical_ranges(text)

    return locate


def _merge_clinical_ranges(
    text: str, spans: tuple[tuple[int, int], ...]
) -> tuple[tuple[int, int], ...]:
    expanded: list[tuple[int, int]] = []
    for span in spans:
        negation = _NEGATION_PREFIX.search(text[: span[0]])
        expanded.append((negation.start() if negation else span[0], span[1]))
    merged: list[tuple[int, int]] = []
    for span in sorted(expanded):
        if merged and (
            span[0] <= merged[-1][1]
            or _RANGE_GAP.fullmatch(text[merged[-1][1] : span[0]]) is not None
        ):
            merged[-1] = (merged[-1][0], max(merged[-1][1], span[1]))
        else:
            merged.append(span)
    return tuple(merged)


def narrative_predicates(text: str) -> tuple[TextRange, ...]:
    """A grammatical action after an explicit person role is not a location.

    Only the verb is protected. Every part of the preceding name still requires
    its own transformation and independent residual check.
    """
    ranges: list[TextRange] = []
    for pattern in _PERSON_ROLE_PATTERNS:
        for person in pattern.finditer(text):
            end = person.end("name")
            predicate = _ROLE_NARRATIVE_VERB.match(text[end:])
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
        for pattern in _AGE_PATTERNS
        for match in pattern.finditer(text)
    )
