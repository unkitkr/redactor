"""Extract corroborating identity evidence from typed columns, never name alone."""

import re

from redactor.policy.dates import parse_date
from redactor.policy.normalization import normalize_digits
from redactor.schemas.identity import IdentityEvidence
from redactor.schemas.redaction import ColumnPolicy, RowEvidence
from redactor.utils.constants import (
    AGE_EXPLICIT_PATTERN,
    AGE_GROUP_MINIMUM,
    FIELD_AGE,
    FIELD_BIRTH_DATE,
    FIELD_DATE,
    FIELD_PATIENT_ID,
    FIELD_PATIENT_NAME,
    FIELD_PROVIDER_ID,
    FIELD_PROVIDER_NAME,
    FIELD_TEXT,
    IDENTITY_PATIENT,
    IDENTITY_PROVIDER,
    MRN_NAMESPACE,
    ROW_CONTEXT_TEMPLATE,
)
from redactor.utils.errors import ERROR_AGE, ERROR_IDENTITY_EVIDENCE


def row_evidence(
    values: tuple[str, ...],
    policies: tuple[ColumnPolicy, ...],
    input_sha256: str,
    row_number: int,
) -> RowEvidence:
    patient_name = _one_value(values, policies, FIELD_PATIENT_NAME)
    patient_id = _one_value(values, policies, FIELD_PATIENT_ID)
    birth = _one_value(values, policies, FIELD_BIRTH_DATE)
    references = [
        parse_date(values[column.index].strip()).value
        for column in policies
        if column.kind == FIELD_DATE and values[column.index].strip()
    ]
    older_age = False
    for column in policies:
        value = values[column.index]
        if column.kind == FIELD_AGE and value.strip():
            if re.fullmatch(r"[0-9]{1,3}\+?", value.strip()) is None:
                raise ValueError(ERROR_AGE)
            older_age |= int(value.strip().rstrip("+")) >= AGE_GROUP_MINIMUM
        elif column.kind == FIELD_TEXT:
            older_age |= any(
                int(match["age"]) >= AGE_GROUP_MINIMUM
                for match in re.finditer(AGE_EXPLICIT_PATTERN, value)
            )
    patient = None
    if patient_name or patient_id or birth:
        namespace = next(
            (
                column.namespace
                for column in policies
                if column.kind == FIELD_PATIENT_ID
            ),
            MRN_NAMESPACE,
        )
        patient = IdentityEvidence(
            role=IDENTITY_PATIENT,
            name=patient_name,
            identifier=canonical_record_identifier(patient_id, namespace)
            if patient_id
            else "",
            identifier_namespace=namespace,
            birth_date=parse_date(birth.strip()).value if birth else None,
            reference_date=max(references) if references else None,
            explicit_older_age=older_age,
            context_key=ROW_CONTEXT_TEMPLATE.format(
                input_sha256=input_sha256, number=row_number, role=IDENTITY_PATIENT
            ),
        )
    provider_name = _one_value(values, policies, FIELD_PROVIDER_NAME)
    provider_id = _one_value(values, policies, FIELD_PROVIDER_ID)
    provider = None
    if provider_name or provider_id:
        namespace = next(
            (
                column.namespace
                for column in policies
                if column.kind == FIELD_PROVIDER_ID
            ),
            "",
        )
        provider = IdentityEvidence(
            role=IDENTITY_PROVIDER,
            name=provider_name,
            identifier=normalize_digits(provider_id) if provider_id else "",
            identifier_namespace=namespace,
            context_key=ROW_CONTEXT_TEMPLATE.format(
                input_sha256=input_sha256, number=row_number, role=IDENTITY_PROVIDER
            ),
        )
    return RowEvidence(patient=patient, provider=provider)


def canonical_record_identifier(value: str, namespace: str) -> str:
    if namespace == MRN_NAMESPACE and re.fullmatch(r"[0-9 -]+", value.strip()):
        return normalize_digits(value)
    return value.strip()


def _one_value(
    values: tuple[str, ...], policies: tuple[ColumnPolicy, ...], kind: str
) -> str:
    matching = {
        values[column.index].strip() for column in policies if column.kind == kind
    }
    matching.discard("")
    if len(matching) > 1:
        raise ValueError(ERROR_IDENTITY_EVIDENCE)
    return next(iter(matching), "")
