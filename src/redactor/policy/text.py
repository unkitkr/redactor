"""Apply explicit text findings, retaining every unedited character exactly."""

from redactor.identity.tabular import canonical_record_identifier
from redactor.policy.contacts import replace_email, replace_phone, replace_street
from redactor.policy.dates import patient_date_offset, shift_date
from redactor.policy.geography import generalize_zip
from redactor.policy.identifiers import replace_identifier, replace_ssn
from redactor.policy.keys import evidence_key
from redactor.policy.names import person_name
from redactor.policy.network import replace_network_address, replace_web_address
from redactor.policy.normalization import normalize_name
from redactor.policy.text_names import mention_name
from redactor.schemas.redaction import TextContext, TextEdit, TextFinding
from redactor.utils.constants import (
    AGE_GROUP_LABEL,
    ENTITY_LOCATION,
    FIELD_ADDRESS,
    FIELD_AGE,
    FIELD_DATE,
    FIELD_EMAIL,
    FIELD_IDENTIFIER,
    FIELD_LOCATION,
    FIELD_NETWORK,
    FIELD_PATIENT_NAME,
    FIELD_PERSON_NAME,
    FIELD_PHONE,
    FIELD_PROVIDER_NAME,
    FIELD_SSN,
    FIELD_WEB,
    FIELD_ZIP,
    IDENTITY_RELATIVE,
    UNLINKED_PERSON_NAMESPACE,
)
from redactor.utils.errors import ERROR_COVERAGE, ERROR_ENTITY_EVIDENCE


def text_edits(
    findings: tuple[TextFinding, ...], context: TextContext, key: bytes
) -> tuple[TextEdit, ...]:
    edits: list[TextEdit] = []
    for finding in findings:
        value = finding.original
        if finding.kind == FIELD_IDENTIFIER:
            replacement = replace_identifier(
                canonical_record_identifier(value, finding.namespace),
                key,
                namespace=finding.namespace,
            )
        elif finding.kind == FIELD_SSN:
            replacement = replace_ssn(value, key)
        elif finding.kind == FIELD_NETWORK:
            replacement = replace_network_address(value, key)
        elif finding.kind == FIELD_WEB:
            replacement = replace_web_address(value, key)
        elif finding.kind == FIELD_ZIP:
            replacement = generalize_zip(value)
        elif finding.kind == FIELD_PHONE:
            replacement = replace_phone(value, key)
        elif finding.kind == FIELD_EMAIL:
            replacement = replace_email(value, key)
        elif finding.kind == FIELD_ADDRESS:
            replacement = replace_street(value, key)
        elif finding.kind == FIELD_DATE:
            offset = (
                context.patient.date_offset_days
                if context.patient
                else patient_date_offset(
                    key, context.context_key, context.maximum_date_shift_days
                )
            )
            replacement = shift_date(value, offset)
        elif finding.kind == FIELD_AGE:
            replacement = AGE_GROUP_LABEL
        elif finding.kind == FIELD_PERSON_NAME:
            identity_key = evidence_key(
                key,
                normalize_name(value),
                namespace=UNLINKED_PERSON_NAMESPACE,
                scope=context.context_key,
            )
            replacement = person_name(identity_key, key, value)
        elif finding.kind in (
            FIELD_PATIENT_NAME,
            FIELD_PROVIDER_NAME,
            IDENTITY_RELATIVE,
        ):
            replacement = mention_name(
                value,
                context,
                key,
                provider=finding.kind == FIELD_PROVIDER_NAME,
                relative=finding.kind == IDENTITY_RELATIVE,
            )
        elif finding.kind in (ENTITY_LOCATION, FIELD_LOCATION):
            location_key = evidence_key(
                key, value.casefold(), namespace=ENTITY_LOCATION
            )
            replacement = person_name(location_key, key).split()[-1]
        else:
            raise ValueError(ERROR_COVERAGE)
        edits.append(TextEdit(**finding.model_dump(), replacement=replacement))
    return tuple(edits)


def apply_text_edits(text: str, edits: tuple[TextEdit, ...]) -> str:
    parts: list[str] = []
    previous = 0
    for edit in edits:
        if (
            edit.start < previous
            or edit.end <= edit.start
            or text[edit.start : edit.end] != edit.original
        ):
            raise ValueError(ERROR_ENTITY_EVIDENCE)
        parts.extend((text[previous : edit.start], edit.replacement))
        previous = edit.end
    parts.append(text[previous:])
    return "".join(parts)
