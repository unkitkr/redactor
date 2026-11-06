"""Locate and transform typed cells while preserving their surrounding table."""

from redactor.formats.tabular_fields import validate_clinical_field
from redactor.identity.tabular import canonical_record_identifier
from redactor.inference.text import find_text_phi
from redactor.policy.ages import generalize_age, replace_birth_date
from redactor.policy.contacts import replace_email, replace_phone, replace_street
from redactor.policy.dates import parse_date, patient_date_offset, shift_date
from redactor.policy.geography import generalize_zip
from redactor.policy.identifiers import (
    replace_identifier,
    replace_lot,
    replace_npi,
    replace_ssn,
)
from redactor.policy.keys import evidence_key
from redactor.policy.names import format_person_name, person_name
from redactor.policy.network import replace_network_address, replace_web_address
from redactor.policy.text import text_edits
from redactor.policy.text_names import mention_name
from redactor.schemas.entities import NerAdapter
from redactor.schemas.redaction import ColumnPolicy, TextContext, TextEdit, TextFinding
from redactor.utils.constants import (
    AGE_GROUP_MINIMUM,
    FIELD_ADDRESS,
    FIELD_AGE,
    FIELD_BIRTH_DATE,
    FIELD_CLINICAL,
    FIELD_DATE,
    FIELD_EMAIL,
    FIELD_IDENTIFIER,
    FIELD_LOCATION,
    FIELD_LOT,
    FIELD_NETWORK,
    FIELD_PATIENT_ID,
    FIELD_PATIENT_NAME,
    FIELD_PERSON_NAME,
    FIELD_PHONE,
    FIELD_PROVIDER_ID,
    FIELD_PROVIDER_NAME,
    FIELD_RELATIVE_NAME,
    FIELD_SSN,
    FIELD_TEXT,
    FIELD_WEB,
    FIELD_ZIP,
    SSN_NAMESPACE,
    SURROGATE_INITIAL_ALPHABET,
)
from redactor.utils.errors import (
    ERROR_AGE_REFERENCE,
    ERROR_COVERAGE,
    ERROR_IDENTIFIER,
    ERROR_IDENTITY_EVIDENCE,
)


def cell_findings(
    value: str,
    policy: ColumnPolicy,
    local_ner: NerAdapter,
    *,
    patient_name: str = "",
    provider_name: str = "",
) -> tuple[TextFinding, ...]:
    if not value.strip():
        return ()
    if policy.kind == FIELD_CLINICAL:
        validate_clinical_field(value, policy.namespace)
        return ()
    if policy.kind == FIELD_TEXT:
        return find_text_phi(
            value, local_ner, patient_name=patient_name, provider_name=provider_name
        )
    if policy.kind in (FIELD_DATE, FIELD_BIRTH_DATE):
        parse_date(value.strip())
    if policy.kind == FIELD_AGE:
        age = int(value.rstrip("+"))
        if age < AGE_GROUP_MINIMUM or generalize_age(age) == value:
            return ()
    if policy.kind == FIELD_ZIP and generalize_zip(value) == value:
        return ()
    return (TextFinding(start=0, end=len(value), original=value, kind=policy.kind),)


def cell_edits(
    value: str,
    policy: ColumnPolicy,
    findings: tuple[TextFinding, ...],
    context: TextContext,
    key: bytes,
) -> tuple[TextEdit, ...]:
    if not findings:
        return ()
    if policy.kind in (FIELD_TEXT, FIELD_PERSON_NAME):
        return text_edits(findings, context, key)
    if len(findings) != 1 or findings[0].original != value:
        raise ValueError(ERROR_COVERAGE)
    identity = (
        context.provider if policy.kind == FIELD_PROVIDER_NAME else context.patient
    )
    if policy.kind in (FIELD_PATIENT_NAME, FIELD_PROVIDER_NAME):
        if identity is None:
            raise ValueError(ERROR_IDENTITY_EVIDENCE)
        replacement = format_person_name(value, identity.surrogate_name)
    elif policy.kind == FIELD_RELATIVE_NAME:
        replacement = format_person_name(
            value, mention_name(value, context, key, provider=False, relative=True)
        )
    elif policy.kind == FIELD_SSN:
        replacement = replace_ssn(value, key)
    elif policy.kind == FIELD_NETWORK:
        replacement = replace_network_address(value, key)
    elif policy.kind == FIELD_WEB:
        replacement = replace_web_address(value, key)
    elif policy.kind == FIELD_PROVIDER_ID:
        replacement = replace_npi(value, key)
    elif policy.kind == FIELD_IDENTIFIER and policy.namespace == SSN_NAMESPACE:
        replacement = replace_ssn(value, key)
    elif policy.kind in (FIELD_PATIENT_ID, FIELD_IDENTIFIER):
        replacement = policy.identifier_prefix + replace_identifier(
            canonical_record_identifier(value, policy.namespace),
            key,
            namespace=policy.namespace,
        )
    elif policy.kind == FIELD_LOT:
        replacement = replace_lot(value, key)
    elif policy.kind in (FIELD_DATE, FIELD_BIRTH_DATE):
        offset = (
            context.patient.date_offset_days
            if context.patient
            else patient_date_offset(
                key, context.context_key, context.maximum_date_shift_days
            )
        )
        if policy.kind == FIELD_BIRTH_DATE:
            if context.patient is None or context.patient.older_age_group is None:
                raise ValueError(ERROR_AGE_REFERENCE)
            replacement = replace_birth_date(
                value.strip(),
                offset,
                older_age_group=context.patient.older_age_group,
                cohort_reference=context.patient.reference_date,
                supports_bounds=policy.supports_date_bounds,
            )
        else:
            replacement = shift_date(value.strip(), offset)
    elif policy.kind == FIELD_AGE:
        replacement = generalize_age(int(value.rstrip("+")))
    elif policy.kind == FIELD_ZIP:
        replacement = generalize_zip(value)
    elif policy.kind == FIELD_PHONE:
        replacement = replace_phone(value, key)
    elif policy.kind == FIELD_EMAIL:
        replacement = replace_email(value, key)
    elif policy.kind == FIELD_ADDRESS:
        replacement = replace_street(value, key)
    elif policy.kind == FIELD_LOCATION:
        replacement = person_name(
            evidence_key(key, value.casefold(), namespace=FIELD_LOCATION), key
        ).split()[-1]
    else:
        raise ValueError(ERROR_COVERAGE)
    if policy.name_part:
        words = replacement.split()
        replacement = words[-1] if policy.name_part == "family" else words[0]
        if policy.name_part == "initial":
            replacement = replacement[0]
            if replacement.casefold() == value.strip().rstrip(".").casefold():
                position = SURROGATE_INITIAL_ALPHABET.index(replacement.upper())
                replacement = SURROGATE_INITIAL_ALPHABET[
                    (position + 1) % len(SURROGATE_INITIAL_ALPHABET)
                ]
    if policy.numeric:
        if not value.isascii() or not value.isdigit() or not replacement.isdigit():
            raise ValueError(ERROR_IDENTIFIER)
        replacement = str(int(replacement))
    return (TextEdit(**findings[0].model_dump(), replacement=replacement),)
