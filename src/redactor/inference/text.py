"""Finish prepared text assessment with grounded model observations."""

import re
from collections.abc import Callable

from redactor.inference.deterministic_text import make_text_preparer, prepare_text_phi
from redactor.inference.evidence import validate_entity_evidence
from redactor.inference.masking import mask_assessed_ranges, restore_entity
from redactor.inference.semantics import possible_entity, refine_entity
from redactor.policy.name_matching import compatible_name_spelling
from redactor.schemas.entities import (
    NerAdapter,
    PreparedTextAssessment,
    TextEntities,
    TextEntity,
)
from redactor.schemas.redaction import TextFinding, TextRange
from redactor.utils.constants import (
    CLINICAL_RANGE_GAP_PATTERN,
    ENTITY_CONTACT,
    ENTITY_IDENTIFIER,
    ENTITY_LOCATION,
    ENTITY_ORGANIZATION,
    ENTITY_PERSON,
    FACILITY_SUFFIX_PATTERN,
    FIELD_EMAIL,
    FIELD_IDENTIFIER,
    FIELD_LOCATION,
    FIELD_NETWORK,
    FIELD_ORGANIZATION,
    FIELD_PATIENT_NAME,
    FIELD_PERSON_NAME,
    FIELD_PHONE,
    FIELD_PROVIDER_NAME,
    FIELD_WEB,
    IDENTITY_RELATIVE,
    NAME_LINE_MAXIMUM_TOKENS,
    NAME_LINE_TOKEN_PATTERN,
    NER_EMAIL_LABEL,
    NER_IDENTIFIER_NAMESPACES,
    NER_IDENTIFIER_VALUE_PATTERN,
    NER_IP_LABEL,
    NER_PHONE_LABEL,
    NER_URL_LABEL,
    ORGANIZATION_CUE_PATTERN,
    ORGANIZATION_FIELD_PATTERN,
    PRESERVED_US_GEOGRAPHY,
    TEXT_EMAIL_PATTERN,
    TEXT_FACILITY_PATTERN,
    TEXT_IPV4_PATTERN,
    TEXT_PHONE_PATTERN,
    TEXT_URL_PATTERN,
)
from redactor.utils.errors import ERROR_COVERAGE, ERROR_ENTITY_EVIDENCE

_FACILITY_BLOCK = re.compile(TEXT_FACILITY_PATTERN)
_FACILITY_SUFFIX_WORD = re.compile(r"\b" + FACILITY_SUFFIX_PATTERN + r"\b")
_ORGANIZATION_CUE = re.compile(ORGANIZATION_CUE_PATTERN)
_ORGANIZATION_FIELD = re.compile(ORGANIZATION_FIELD_PATTERN)
_IDENTIFIER_VALUE = re.compile(NER_IDENTIFIER_VALUE_PATTERN)
_NAME_LINE_TOKEN = re.compile(NAME_LINE_TOKEN_PATTERN)
_SURFACE_CHARACTER = re.compile(CLINICAL_RANGE_GAP_PATTERN)
_CONTACT_SYNTAX = tuple(
    (label, re.compile(pattern), kind)
    for label, pattern, kind in (
        (NER_PHONE_LABEL, TEXT_PHONE_PATTERN, FIELD_PHONE),
        (NER_EMAIL_LABEL, TEXT_EMAIL_PATTERN, FIELD_EMAIL),
        (NER_URL_LABEL, TEXT_URL_PATTERN, FIELD_WEB),
        (NER_IP_LABEL, TEXT_IPV4_PATTERN, FIELD_NETWORK),
    )
)


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


def make_text_finder(
    local_ner: NerAdapter,
    *,
    maximum_entries: int,
    maximum_text_characters: int,
) -> Callable[[str, str, str], tuple[TextFinding, ...]]:
    """Prepare repeated text efficiently without caching identity decisions."""
    prepare = make_text_preparer(
        maximum_entries=maximum_entries,
        maximum_text_characters=maximum_text_characters,
    )

    def find(
        text: str, patient_name: str, provider_name: str
    ) -> tuple[TextFinding, ...]:
        return finish_text_phi(prepare(text, patient_name, provider_name), local_ner)

    return find


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
        if entity.entity_type == ENTITY_ORGANIZATION:
            # A lone capitalized name line carries a person, not a facility.
            grounded = _person_on_name_line(text, entity, tuple(findings))
            if grounded is None:
                continue
            entity = grounded
        if entity.entity_type in (ENTITY_ORGANIZATION, ENTITY_LOCATION):
            if any(
                finding.kind == FIELD_ORGANIZATION
                and finding.start <= entity.start
                and entity.end <= finding.end
                and _FACILITY_BLOCK.fullmatch(finding.original)
                for finding in findings
            ):
                # The complete facility replacement already covers this second
                # grounded fragment. A span extending outside it is not covered.
                continue
            for facility in _FACILITY_BLOCK.finditer(text):
                if (
                    facility.start() <= entity.start
                    and entity.end <= facility.end()
                    and not any(
                        facility.start() < span.end and span.start < facility.end()
                        for span in prepared.protected
                    )
                    and not any(
                        facility.start() < finding.end
                        and finding.start < facility.end()
                        for finding in findings
                    )
                ):
                    # A grounded partial organization or location can establish
                    # the full syntactic facility phrase on the same line.
                    entity = entity.model_copy(
                        update={
                            "start": facility.start(),
                            "end": facility.end(),
                            "text": facility[0],
                            "entity_type": ENTITY_ORGANIZATION,
                        }
                    )
                    break
        if entity.entity_type in (ENTITY_ORGANIZATION, ENTITY_LOCATION):
            # A grounded organization or location must not absorb the protected
            # clinical tokens (labels, codes, doses) that adjoin its span.
            trimmed = _trim_protected_overlap(text, entity, prepared.protected)
            if trimmed is None:
                continue
            entity = trimmed
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
            _ORGANIZATION_CUE.search(entity.text)
            or _ORGANIZATION_FIELD.search(text[: entity.start])
        ):
            entity_kind = FIELD_ORGANIZATION
        elif entity.entity_type == ENTITY_IDENTIFIER and entity.label in dict(
            NER_IDENTIFIER_NAMESPACES
        ):
            if any(character.isdigit() for character in entity.text) and (
                _IDENTIFIER_VALUE.fullmatch(entity.text)
            ):
                entity_kind = FIELD_IDENTIFIER
                namespace = dict(NER_IDENTIFIER_NAMESPACES)[entity.label]
        elif entity.entity_type == ENTITY_CONTACT:
            # A contact label grounds only on its complete supported syntax;
            # any other shape stays unassessed instead of being accepted.
            for label, syntax, kind in _CONTACT_SYNTAX:
                if entity.label == label and syntax.fullmatch(entity.text):
                    entity_kind = kind
                    break
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


def _trim_protected_overlap(
    text: str, entity: TextEntity, protected: tuple[TextRange, ...]
) -> TextEntity | None:
    """Trim a trailing protected overlap from a grounded organization span.

    Model spans can reach into an adjoining protected clinical token such as a
    field label. The ungroundable remainder is dropped, keeping the clinical
    token byte-for-byte instead of failing the whole record.
    """
    overlapping = [
        span
        for span in protected
        if entity.start < span.end and span.start < entity.end
    ]
    if not overlapping:
        return entity
    boundary = min(span.start for span in overlapping)
    if boundary <= entity.start:
        return None
    end = boundary
    while end > entity.start and _SURFACE_CHARACTER.fullmatch(text[end - 1]):
        end -= 1
    value = text[entity.start : end]
    if not any(character.isalnum() for character in value):
        return None
    return entity.model_copy(update={"end": end, "text": value})


def _person_on_name_line(
    text: str, entity: TextEntity, findings: tuple[TextFinding, ...]
) -> TextEntity | None:
    """Ground a mislabeled organization token as the name line it belongs to.

    The observation must be one capitalized word on a line built only from
    short capitalized name tokens: no digits, roles, labels or organization
    vocabulary. The finding then spans the whole name so both components are
    pseudonymized as a person. None drops an observation already covered by a
    grounded name on the same line; the unchanged entity keeps the fail-closed
    organization path for every other shape.
    """
    if " " in entity.text or not _NAME_LINE_TOKEN.fullmatch(entity.text):
        return entity
    if any(character.isdigit() for character in entity.text):
        return entity
    line_start = (
        max(text.rfind("\n", 0, entity.start), text.rfind("\r", 0, entity.start)) + 1
    )
    line_end = min(
        (
            index
            for index in (text.find("\n", entity.end), text.find("\r", entity.end))
            if index >= 0
        ),
        default=len(text),
    )
    line = text[line_start:line_end]
    tokens = [token.strip(",.") for token in line.split() if token.strip(",.")]
    if not 2 <= len(tokens) <= NAME_LINE_MAXIMUM_TOKENS:
        return entity
    if not all(_NAME_LINE_TOKEN.fullmatch(token) for token in tokens):
        return entity
    if any(any(character.isdigit() for character in token) for token in tokens):
        return entity
    if any(
        _ORGANIZATION_CUE.search(token) or _FACILITY_SUFFIX_WORD.search(token)
        for token in tokens
    ):
        return entity
    start = line_start + len(line) - len(line.lstrip())
    value = line.strip()
    end = start + len(value)
    for found in findings:
        if found.start <= entity.start and entity.end <= found.end:
            if found.kind in (
                FIELD_PATIENT_NAME,
                FIELD_PROVIDER_NAME,
                FIELD_PERSON_NAME,
                IDENTITY_RELATIVE,
            ):
                return None  # A grounded name already covers this token.
            return entity
    if any(start < found.end and found.start < end for found in findings):
        return entity
    return entity.model_copy(
        update={"start": start, "end": end, "text": value, "entity_type": ENTITY_PERSON}
    )


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
