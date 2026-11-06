"""Finish prepared text assessment with grounded model observations."""

import re

from redactor.inference.deterministic_text import prepare_text_phi
from redactor.inference.evidence import validate_entity_evidence
from redactor.inference.masking import mask_assessed_ranges, restore_entity
from redactor.inference.semantics import possible_entity, refine_entity
from redactor.policy.name_matching import compatible_name_spelling
from redactor.schemas.entities import NerAdapter, PreparedTextAssessment, TextEntities
from redactor.schemas.redaction import TextFinding, TextRange
from redactor.utils.constants import (
    ENTITY_IDENTIFIER,
    ENTITY_LOCATION,
    ENTITY_ORGANIZATION,
    ENTITY_PERSON,
    FIELD_IDENTIFIER,
    FIELD_LOCATION,
    FIELD_ORGANIZATION,
    FIELD_PATIENT_NAME,
    FIELD_PERSON_NAME,
    FIELD_PROVIDER_NAME,
    NER_IDENTIFIER_NAMESPACES,
    NER_IDENTIFIER_VALUE_PATTERN,
    ORGANIZATION_CUE_PATTERN,
    ORGANIZATION_FIELD_PATTERN,
    PRESERVED_US_GEOGRAPHY,
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
    return finish_text_phi(
        prepare_text_phi(text, patient_name=patient_name, provider_name=provider_name),
        local_ner,
    )


def finish_text_phi(
    prepared: PreparedTextAssessment, local_ner: NerAdapter
) -> tuple[TextFinding, ...]:
    """Run the model only when deterministic evidence leaves unresolved text."""
    text = prepared.text
    findings = list(prepared.findings)
    if not prepared.unresolved:
        return _checked_findings(text, tuple(findings))
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
            for region in prepared.protected
        ):
            continue
        entity_kind = None
        namespace = ""
        if entity.entity_type == ENTITY_PERSON:
            patient_match = bool(prepared.patient_name) and compatible_name_spelling(
                entity.text, prepared.patient_name, allow_surname=True
            )
            provider_match = bool(prepared.provider_name) and compatible_name_spelling(
                entity.text, prepared.provider_name, allow_surname=True
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
    return _checked_findings(text, tuple(findings))


def _checked_findings(
    text: str, findings: tuple[TextFinding, ...]
) -> tuple[TextFinding, ...]:
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
