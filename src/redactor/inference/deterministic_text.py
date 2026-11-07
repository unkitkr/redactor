"""Prepare deterministic text evidence without loading or invoking a model."""

import re
from collections.abc import Callable
from functools import lru_cache
from ipaddress import ip_address

from redactor.policy.dates import parse_date
from redactor.policy.name_mentions import known_name_ranges, make_name_matcher
from redactor.policy.text_patterns import (
    age_mentions,
    clinical_ranges,
    make_clinical_matcher,
)
from redactor.schemas.entities import PreparedTextAssessment
from redactor.schemas.redaction import TextFinding, TextRange
from redactor.utils.constants import (
    AGE_GROUP_MINIMUM,
    FIELD_ADDRESS,
    FIELD_AGE,
    FIELD_DATE,
    FIELD_EMAIL,
    FIELD_IDENTIFIER,
    FIELD_NETWORK,
    FIELD_ORGANIZATION,
    FIELD_PATIENT_NAME,
    FIELD_PERSON_NAME,
    FIELD_PHONE,
    FIELD_PROVIDER_NAME,
    FIELD_SSN,
    FIELD_WEB,
    FIELD_ZIP,
    IDENTITY_RELATIVE,
    MRN_NAMESPACE,
    NAME_ADJACENT_IDENTIFIER_PATTERN,
    SSN_NAMESPACE,
    TEXT_DATE_PATTERN,
    TEXT_EMAIL_PATTERN,
    TEXT_FACILITY_LABEL_PATTERN,
    TEXT_FACILITY_PATTERN,
    TEXT_IDENTIFIER_PATTERNS,
    TEXT_IPV4_PATTERN,
    TEXT_NAMED_DATE_PATTERN,
    TEXT_PHONE_PATTERN,
    TEXT_PROVIDER_PATTERN,
    TEXT_RELATIVE_PATTERN,
    TEXT_STREET_PATTERN,
    TEXT_URL_PATTERN,
    TEXT_ZIP_PATTERN,
)
from redactor.utils.errors import ERROR_ENTITY_EVIDENCE

_FINDING_PATTERNS = tuple(
    (re.compile(pattern), kind)
    for pattern, kind in (
        (TEXT_URL_PATTERN, FIELD_WEB),
        (TEXT_IPV4_PATTERN, FIELD_NETWORK),
        (TEXT_ZIP_PATTERN, FIELD_ZIP),
        (TEXT_EMAIL_PATTERN, FIELD_EMAIL),
        (TEXT_PHONE_PATTERN, FIELD_PHONE),
        (TEXT_DATE_PATTERN, FIELD_DATE),
        (TEXT_NAMED_DATE_PATTERN, FIELD_DATE),
        (TEXT_STREET_PATTERN, FIELD_ADDRESS),
        (TEXT_RELATIVE_PATTERN, IDENTITY_RELATIVE),
        (TEXT_PROVIDER_PATTERN, FIELD_PROVIDER_NAME),
        (TEXT_FACILITY_PATTERN, FIELD_ORGANIZATION),
        (TEXT_FACILITY_LABEL_PATTERN, FIELD_ORGANIZATION),
    )
)
_IDENTIFIER_PATTERNS = tuple(
    (re.compile(pattern), namespace) for pattern, namespace in TEXT_IDENTIFIER_PATTERNS
)
_NAME_ADJACENT_IDENTIFIER = re.compile(NAME_ADJACENT_IDENTIFIER_PATTERN)


def prepare_text_phi(
    text: str,
    *,
    patient_name: str = "",
    provider_name: str = "",
) -> PreparedTextAssessment:
    """Keep source offsets and role evidence in a serializable private value."""
    findings, protected = _deterministic_findings(
        text, _FINDING_PATTERNS, _IDENTIFIER_PATTERNS, clinical_ranges
    )
    return _bind_names(
        text,
        findings,
        protected,
        patient_name,
        provider_name,
        known_name_ranges,
        known_name_ranges,
    )


def make_text_preparer(
    *, maximum_entries: int, maximum_text_characters: int
) -> Callable[[str, str, str], PreparedTextAssessment]:
    """Reuse bounded, context-free evidence; bind actual names on every call."""
    clinical = make_clinical_matcher()
    patient_matches = make_name_matcher(
        maximum_entries=maximum_entries,
        maximum_name_characters=maximum_text_characters,
    )
    provider_matches = make_name_matcher(
        maximum_entries=maximum_entries,
        maximum_name_characters=maximum_text_characters,
    )

    def assess(text: str) -> tuple[tuple[TextFinding, ...], tuple[TextRange, ...]]:
        return _deterministic_findings(
            text, _FINDING_PATTERNS, _IDENTIFIER_PATTERNS, clinical
        )

    cached = lru_cache(maxsize=maximum_entries)(assess)

    def prepare(
        text: str, patient_name: str, provider_name: str
    ) -> PreparedTextAssessment:
        findings, protected = (
            cached(text) if len(text) <= maximum_text_characters else assess(text)
        )
        return _bind_names(
            text,
            findings,
            protected,
            patient_name,
            provider_name,
            patient_matches,
            provider_matches,
        )

    return prepare


def _deterministic_findings(
    text: str,
    patterns: tuple[tuple[re.Pattern[str], str], ...],
    identifiers: tuple[tuple[re.Pattern[str], str], ...],
    clinical: Callable[[str], tuple[TextRange, ...]],
) -> tuple[tuple[TextFinding, ...], tuple[TextRange, ...]]:
    protected = list(clinical(text))
    findings: list[TextFinding] = []
    for pattern, kind in patterns:
        for match in pattern.finditer(text):
            group = (
                "name"
                if "name" in match.re.groupindex
                else ("value" if "value" in match.re.groupindex else 0)
            )
            start, end = match.span(group)
            if any(
                start < existing.end and end > existing.start for existing in findings
            ):
                continue
            if any(start < region.end and end > region.start for region in protected):
                continue
            value = text[start:end]
            if kind == FIELD_DATE:
                parse_date(value)
            if kind == FIELD_NETWORK:
                ip_address(value)
            findings.append(
                TextFinding(start=start, end=end, original=value, kind=kind)
            )
    for pattern, namespace in identifiers:
        for match in pattern.finditer(text):
            start, end = match.span("value")
            if any(start < found.end and end > found.start for found in findings):
                continue
            findings.append(
                TextFinding(
                    start=start,
                    end=end,
                    original=text[start:end],
                    kind=FIELD_SSN if namespace == SSN_NAMESPACE else FIELD_IDENTIFIER,
                    namespace=namespace,
                )
            )
    for expression, number, age in age_mentions(text):
        protected.append(
            TextRange(
                start=expression.start,
                end=expression.end
                + int(text[expression.end : expression.end + 1] == "+"),
            )
        )
        if age >= AGE_GROUP_MINIMUM:
            has_plus = text[number.end : number.end + 1] == "+"
            if has_plus and age == AGE_GROUP_MINIMUM:
                continue
            findings.append(
                TextFinding(
                    start=number.start,
                    end=number.end + int(has_plus),
                    original=text[number.start : number.end + int(has_plus)],
                    kind=FIELD_AGE,
                )
            )
    return tuple(findings), tuple(protected)


def _bind_names(
    text: str,
    base_findings: tuple[TextFinding, ...],
    protected: tuple[TextRange, ...],
    patient_name: str,
    provider_name: str,
    patient_matches: Callable[[str, str], tuple[TextRange, ...]],
    provider_matches: Callable[[str, str], tuple[TextRange, ...]],
) -> PreparedTextAssessment:
    findings = list(base_findings)
    # A model is not needed to rediscover a corroborated full name or initial
    # spelling already present in this record's typed identity fields.
    mentions: dict[tuple[int, int], set[str]] = {}
    for name, kind, locate in (
        (patient_name, FIELD_PATIENT_NAME, patient_matches),
        (provider_name, FIELD_PROVIDER_NAME, provider_matches),
    ):
        for span in locate(text, name):
            mentions.setdefault((span.start, span.end), set()).add(kind)
    for (start, end), roles in sorted(mentions.items()):
        if any(start < found.end and end > found.start for found in findings):
            continue
        findings.append(
            TextFinding(
                start=start,
                end=end,
                original=text[start:end],
                kind=next(iter(roles)) if len(roles) == 1 else FIELD_PERSON_NAME,
            )
        )
    if mentions:
        # A model is not needed to keep an unlabeled identifier that travels
        # with this record's corroborated name in the same free-text value.
        findings.extend(_name_adjacent_identifiers(text, findings, protected, mentions))
    assessed = tuple(TextRange(start=f.start, end=f.end) for f in findings)
    return PreparedTextAssessment(
        text=text,
        patient_name=patient_name,
        provider_name=provider_name,
        findings=tuple(findings),
        protected=tuple(protected),
        unresolved=_unresolved_ranges(text, (*assessed, *protected)),
    )


def _name_adjacent_identifiers(
    text: str,
    findings: list[TextFinding],
    protected: tuple[TextRange, ...],
    mentions: dict[tuple[int, int], set[str]],
) -> tuple[TextFinding, ...]:
    """Bind bare identifier digits to the name that shares their value.

    Residual risk: a 6+ digit quantity sharing a free-text value with the
    record's patient or provider name is pseudonymized as that person's
    identifier. This accepted tradeoff closes unlabeled patient-id leaks that
    neither labelled patterns nor the model reliably catch.
    """
    namespace = (
        MRN_NAMESPACE
        if any(FIELD_PATIENT_NAME in roles for roles in mentions.values())
        else "identifier"
    )
    located: list[TextFinding] = []
    for match in _NAME_ADJACENT_IDENTIFIER.finditer(text):
        start, end = match.span()
        value = text[start:end]
        try:
            parse_date(value)
        except ValueError:
            pass
        else:
            continue  # A complete compact calendar date is not an identifier.
        if any(start < found.end and found.start < end for found in findings):
            continue
        if any(start < region.end and region.start < end for region in protected):
            continue
        located.append(
            TextFinding(
                start=start,
                end=end,
                original=value,
                kind=FIELD_IDENTIFIER,
                namespace=namespace,
            )
        )
    return tuple(located)


def _unresolved_ranges(
    text: str, assessed: tuple[TextRange, ...]
) -> tuple[TextRange, ...]:
    """Only validated spans and whitespace are exempt from model assessment."""
    unresolved: list[TextRange] = []
    previous = 0
    for span in sorted(assessed, key=lambda item: (item.start, item.end)):
        if not (0 <= span.start < span.end <= len(text)):
            raise ValueError(ERROR_ENTITY_EVIDENCE)
        if previous < span.start and text[previous : span.start].strip():
            unresolved.append(TextRange(start=previous, end=span.start))
        previous = max(previous, span.end)
    if previous < len(text) and text[previous:].strip():
        unresolved.append(TextRange(start=previous, end=len(text)))
    return tuple(unresolved)
