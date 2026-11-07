"""Find independent source evidence without authorizing identity merges or edits."""

import re
from ipaddress import IPv6Address
from unicodedata import category

from redactor.policy.name_mentions import known_name_ranges as known_name_ranges
from redactor.schemas.redaction import TextRange
from redactor.utils.constants import (
    VERIFIER_CONTACT_CANDIDATE_PATTERN,
    VERIFIER_CONTACT_INTERNATIONAL_PREFIXES,
    VERIFIER_CONTACT_MINIMUM_DIGITS,
    VERIFIER_FACILITY_PATTERN,
    VERIFIER_IPV6_CANDIDATE_PATTERN,
    VERIFIER_LABEL_VALUE_END_PATTERN,
    VERIFIER_LABELLED_VALUE_PATTERN,
    VERIFIER_RESIDUAL_PATTERNS,
    VERIFIER_SIGNED_DECIMAL_PATTERN,
)

_RESIDUAL_PATTERNS = tuple(
    re.compile(pattern)
    for pattern in (*VERIFIER_RESIDUAL_PATTERNS, VERIFIER_FACILITY_PATTERN)
)
_LABELLED_VALUE = re.compile(VERIFIER_LABELLED_VALUE_PATTERN)
_LABEL_VALUE_END = re.compile(VERIFIER_LABEL_VALUE_END_PATTERN)
_CONTACT_CANDIDATE = re.compile(VERIFIER_CONTACT_CANDIDATE_PATTERN)
_IPV6_CANDIDATE = re.compile(VERIFIER_IPV6_CANDIDATE_PATTERN)
_SIGNED_DECIMAL = re.compile(VERIFIER_SIGNED_DECIMAL_PATTERN)


def contains_range(outer: TextRange, inner: TextRange) -> bool:
    return outer.start <= inner.start and inner.end <= outer.end


def covered_by_ranges(
    text: str, mention: TextRange, evidence: tuple[TextRange, ...]
) -> bool:
    """Cover every substantive character with exact, location-bound evidence.

    Model spans can join a verified edit to an unchanged clinical expression.
    Whitespace and punctuation may join those proofs; letters, marks, symbols
    and numbers outside them remain unresolved, including a single initial.
    """
    cursor = mention.start
    covered = False
    for span in sorted(evidence, key=lambda item: (item.start, item.end)):
        if span.end <= cursor or span.start >= mention.end:
            continue
        gap = text[cursor : min(span.start, mention.end)]
        if any(
            not (value.isspace() or category(value).startswith("P")) for value in gap
        ):
            return False
        cursor = max(cursor, span.end)
        covered = True
        if cursor >= mention.end:
            return True
    return covered and all(
        value.isspace() or category(value).startswith("P")
        for value in text[cursor : mention.end]
    )


def sensitive_ranges(
    text: str,
    clinical: tuple[TextRange, ...],
    *,
    patient_name: str,
    provider_name: str,
) -> tuple[TextRange, ...]:
    """Conflicting labels/name evidence outranks generic clinical shape matches."""
    found: list[TextRange] = []
    for pattern in _RESIDUAL_PATTERNS:
        for match in pattern.finditer(text):
            group = "value" if "value" in match.re.groupindex else 0
            found.append(TextRange(start=match.start(group), end=match.end(group)))
    for match in _LABELLED_VALUE.finditer(text):
        value = match["value"]
        boundary = _LABEL_VALUE_END.search(value)
        value = value[: boundary.start()] if boundary else value
        value = value.rstrip(". \t")
        if value:
            found.append(
                TextRange(
                    start=match.start("value"), end=match.start("value") + len(value)
                )
            )
    for match in _CONTACT_CANDIDATE.finditer(text):
        digits = sum(character.isdigit() for character in match["number"])
        if digits < VERIFIER_CONTACT_MINIMUM_DIGITS:
            continue
        candidate = TextRange(start=match.start(), end=match.end())
        if not _clinical_number(match["number"], candidate, clinical):
            found.append(candidate)
    for match in _IPV6_CANDIDATE.finditer(text):
        value = match[0].rstrip(".")
        try:
            IPv6Address(value)
        except ValueError:
            continue
        found.append(TextRange(start=match.start(), end=match.start() + len(value)))
    for name in (patient_name, provider_name):
        found.extend(known_name_ranges(text, name))
    return tuple(found)


def _clinical_number(
    number: str, candidate: TextRange, clinical: tuple[TextRange, ...]
) -> bool:
    """An international prefix conflicts with a generic number-and-unit match."""
    if number.startswith(VERIFIER_CONTACT_INTERNATIONAL_PREFIXES):
        # A single decimal point and a clinical unit establish a signed decimal
        # measurement. Unseparated international digits remain ambiguous even
        # when followed by a unit, and therefore require coverage or quarantine.
        if _SIGNED_DECIMAL.fullmatch(number) is None:
            return False
        candidate = TextRange(start=candidate.start + 1, end=candidate.end)
    return any(contains_range(span, candidate) for span in clinical)
