"""Combine grounded model observations with typed patterns and clinical context."""

import re
from ipaddress import ip_address

from redactor.inference.evidence import validate_entity_evidence
from redactor.inference.masking import mask_assessed_ranges, restore_entity
from redactor.inference.semantics import possible_entity, refine_entity
from redactor.policy.dates import parse_date
from redactor.policy.name_matching import compatible_name_spelling
from redactor.policy.name_mentions import known_name_ranges
from redactor.policy.text_patterns import age_mentions, clinical_ranges
from redactor.schemas.entities import NerAdapter, TextEntities
from redactor.schemas.redaction import TextFinding, TextRange
from redactor.utils.constants import (
    AGE_GROUP_MINIMUM,
    ENTITY_IDENTIFIER,
    ENTITY_LOCATION,
    ENTITY_ORGANIZATION,
    ENTITY_PERSON,
    FIELD_ADDRESS,
    FIELD_AGE,
    FIELD_DATE,
    FIELD_EMAIL,
    FIELD_IDENTIFIER,
    FIELD_LOCATION,
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
    NER_IDENTIFIER_NAMESPACES,
    NER_IDENTIFIER_VALUE_PATTERN,
    ORGANIZATION_CUE_PATTERN,
    ORGANIZATION_FIELD_PATTERN,
    PRESERVED_US_GEOGRAPHY,
    SSN_NAMESPACE,
    TEXT_DATE_PATTERN,
    TEXT_EMAIL_PATTERN,
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
    ):
        for match in re.finditer(pattern, text):
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
    for pattern, namespace in TEXT_IDENTIFIER_PATTERNS:
        for match in re.finditer(pattern, text):
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
    # A model is not needed to rediscover a corroborated full name or initial
    # spelling already present in this record's typed identity fields.
    mentions: dict[tuple[int, int], set[str]] = {}
    for name, kind in (
        (patient_name, FIELD_PATIENT_NAME),
        (provider_name, FIELD_PROVIDER_NAME),
    ):
        for span in known_name_ranges(text, name):
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
    # Keep clinical context visible to the model. Replacing diseases and doses
    # with mask tokens changes the meaning around otherwise unlinked people.
    masks = tuple(TextRange(start=f.start, end=f.end) for f in findings)
    masked, positions = mask_assessed_ranges(text, masks)
    observations = validate_entity_evidence(
        masked, TextEntities(entities=local_ner(masked))
    )
    for observed in observations:
        if not possible_entity(observed, masked):
            continue
        entity = restore_entity(text, observed, positions)
        if entity is None or not possible_entity(entity, text):
            continue
        entity = refine_entity(entity)
        if any(
            region.start <= entity.start and entity.end <= region.end
            for region in protected
        ):
            continue
        entity_kind = None
        namespace = ""
        if entity.entity_type == ENTITY_PERSON:
            patient_match = bool(patient_name) and compatible_name_spelling(
                entity.text, patient_name, allow_surname=True
            )
            provider_match = bool(provider_name) and compatible_name_spelling(
                entity.text, provider_name, allow_surname=True
            )
            if patient_match and not provider_match:
                entity_kind = FIELD_PATIENT_NAME
            elif provider_match and not patient_match:
                entity_kind = FIELD_PROVIDER_NAME
            else:
                entity_kind = FIELD_PERSON_NAME
        elif entity.entity_type == ENTITY_LOCATION:
            if entity.text.casefold().strip() in PRESERVED_US_GEOGRAPHY:
                continue
            entity_kind = FIELD_LOCATION
        elif entity.entity_type == ENTITY_ORGANIZATION and (
            re.search(ORGANIZATION_CUE_PATTERN, entity.text)
            or re.search(ORGANIZATION_FIELD_PATTERN, text[: entity.start])
        ):
            entity_kind = FIELD_ORGANIZATION
        elif entity.entity_type == ENTITY_IDENTIFIER and entity.label in dict(
            NER_IDENTIFIER_NAMESPACES
        ):
            if any(character.isdigit() for character in entity.text) and re.fullmatch(
                NER_IDENTIFIER_VALUE_PATTERN, entity.text
            ):
                entity_kind = FIELD_IDENTIFIER
                namespace = dict(NER_IDENTIFIER_NAMESPACES)[entity.label]
        if entity_kind is None:
            raise ValueError(ERROR_COVERAGE)
        findings.append(
            TextFinding(
                start=entity.start,
                end=entity.end,
                original=entity.text,
                kind=entity_kind,
                namespace=namespace,
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
