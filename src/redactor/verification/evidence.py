"""Find independent source evidence without authorizing identity merges or edits."""

import re
from ipaddress import IPv6Address

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


def contains_range(outer: TextRange, inner: TextRange) -> bool:
    return outer.start <= inner.start and inner.end <= outer.end


def sensitive_ranges(
    text: str,
    clinical: tuple[TextRange, ...],
    *,
    patient_name: str,
    provider_name: str,
) -> tuple[TextRange, ...]:
    """Conflicting labels/name evidence outranks generic clinical shape matches."""
    found: list[TextRange] = []
    for pattern in (*VERIFIER_RESIDUAL_PATTERNS, VERIFIER_FACILITY_PATTERN):
        for match in re.finditer(pattern, text):
            group = "value" if "value" in match.re.groupindex else 0
            found.append(TextRange(start=match.start(group), end=match.end(group)))
    for match in re.finditer(VERIFIER_LABELLED_VALUE_PATTERN, text):
        value = match["value"]
        boundary = re.search(VERIFIER_LABEL_VALUE_END_PATTERN, value)
        value = value[: boundary.start()] if boundary else value
        value = value.rstrip(". \t")
        if value:
            found.append(
                TextRange(
                    start=match.start("value"), end=match.start("value") + len(value)
                )
            )
    for match in re.finditer(VERIFIER_CONTACT_CANDIDATE_PATTERN, text):
        digits = sum(character.isdigit() for character in match["number"])
        if digits < VERIFIER_CONTACT_MINIMUM_DIGITS:
            continue
        candidate = TextRange(start=match.start(), end=match.end())
        if not _clinical_number(match["number"], candidate, clinical):
            found.append(candidate)
    for match in re.finditer(VERIFIER_IPV6_CANDIDATE_PATTERN, text):
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
        if re.fullmatch(VERIFIER_SIGNED_DECIMAL_PATTERN, number) is None:
            return False
        candidate = TextRange(start=candidate.start + 1, end=candidate.end)
    return any(contains_range(span, candidate) for span in clinical)
