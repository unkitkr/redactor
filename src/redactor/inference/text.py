"""Combine grounded model observations with typed patterns and clinical context."""

import re

from redactor.inference.evidence import validate_entity_evidence
from redactor.inference.masking import mask_assessed_ranges, restore_entity
from redactor.policy.dates import parse_date
from redactor.policy.normalization import normalize_name
from redactor.policy.text_patterns import age_mentions, clinical_ranges
from redactor.schemas.entities import NerAdapter, TextEntities
from redactor.schemas.redaction import TextFinding, TextRange
from redactor.utils.constants import (
    AGE_GROUP_MINIMUM,
    ENTITY_LOCATION,
    ENTITY_PERSON,
    FIELD_ADDRESS,
    FIELD_AGE,
    FIELD_DATE,
    FIELD_EMAIL,
    FIELD_PATIENT_NAME,
    FIELD_PHONE,
    FIELD_PROVIDER_NAME,
    IDENTITY_RELATIVE,
    TEXT_DATE_PATTERN,
    TEXT_EMAIL_PATTERN,
    TEXT_NAMED_DATE_PATTERN,
    TEXT_PHONE_PATTERN,
    TEXT_PROVIDER_PATTERN,
    TEXT_RELATIVE_PATTERN,
    TEXT_STREET_PATTERN,
)
from redactor.utils.errors import ERROR_COVERAGE, ERROR_ENTITY_EVIDENCE


def find_text_phi(
    text: str,
    local_ner: NerAdapter,
    *,
    patient_name: str = "",
    provider_name: str = "",
) -> tuple[TextFinding, ...]:
    """An unresolved model observation is not silently accepted as clinical text."""
    protected = list(clinical_ranges(text))
    findings: list[TextFinding] = []
    for pattern, kind in (
        (TEXT_EMAIL_PATTERN, FIELD_EMAIL),
        (TEXT_PHONE_PATTERN, FIELD_PHONE),
        (TEXT_DATE_PATTERN, FIELD_DATE),
        (TEXT_NAMED_DATE_PATTERN, FIELD_DATE),
        (TEXT_STREET_PATTERN, FIELD_ADDRESS),
        (TEXT_RELATIVE_PATTERN, IDENTITY_RELATIVE),
        (TEXT_PROVIDER_PATTERN, FIELD_PROVIDER_NAME),
    ):
        for match in re.finditer(pattern, text):
            group = "name" if "name" in match.re.groupindex else 0
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
            findings.append(
                TextFinding(start=start, end=end, original=value, kind=kind)
            )
    for expression, number, age in age_mentions(text):
        protected.append(expression)
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
    masks = tuple(protected) + tuple(
        TextRange(start=f.start, end=f.end) for f in findings
    )
    masked, positions = mask_assessed_ranges(text, masks)
    observations = validate_entity_evidence(
        masked, TextEntities(entities=local_ner(masked))
    )
    for observed in observations:
        entity = restore_entity(text, observed, positions)
        if entity is None:
            continue
        entity_kind = None
        if entity.entity_type == ENTITY_PERSON:
            name = normalize_name(entity.text)
            if patient_name and name == normalize_name(patient_name):
                entity_kind = FIELD_PATIENT_NAME
            elif provider_name and name == normalize_name(provider_name):
                entity_kind = FIELD_PROVIDER_NAME
        elif entity.entity_type == ENTITY_LOCATION:
            if any(
                finding.kind == FIELD_ADDRESS
                and finding.end <= entity.start
                and not text[finding.end : entity.start].strip(" ,\r\n")
                for finding in findings
            ):
                entity_kind = ENTITY_LOCATION
        if entity_kind is None:
            raise ValueError(ERROR_COVERAGE)
        findings.append(
            TextFinding(
                start=entity.start,
                end=entity.end,
                original=entity.text,
                kind=entity_kind,
            )
        )
    ordered = tuple(sorted(findings, key=lambda finding: (finding.start, finding.end)))
    previous_end = 0
    for finding in ordered:
        if (
            finding.start < previous_end
            or text[finding.start : finding.end] != finding.original
        ):
            raise ValueError(ERROR_ENTITY_EVIDENCE)
        previous_end = finding.end
    return ordered
