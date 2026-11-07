"""Extract corroborating identity evidence from typed columns, never name alone."""

import re
from collections.abc import Callable
from datetime import date
from functools import lru_cache

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
    TABULAR_CACHE_ENTRIES,
    TABULAR_CACHE_VALUE_CHARACTERS,
)
from redactor.utils.errors import ERROR_AGE, ERROR_IDENTITY_EVIDENCE


def row_evidence(
    values: tuple[str, ...],
    policies: tuple[ColumnPolicy, ...],
    input_sha256: str,
    row_number: int,
) -> RowEvidence:
    return make_row_evidence(policies, input_sha256)(values, row_number)


def make_row_evidence(
    policies: tuple[ColumnPolicy, ...], input_sha256: str
) -> Callable[[tuple[str, ...], int], RowEvidence]:
    """Compile column lookup once, retaining each row's evidence and context."""
    grouped: dict[str, list[int]] = {}
    for column in policies:
        grouped.setdefault(column.kind, []).append(column.index)
    indexes = {kind: tuple(values) for kind, values in grouped.items()}
    patient_name_indexes = indexes.get(FIELD_PATIENT_NAME, ())
    patient_id_indexes = indexes.get(FIELD_PATIENT_ID, ())
    birth_indexes = indexes.get(FIELD_BIRTH_DATE, ())
    provider_name_indexes = indexes.get(FIELD_PROVIDER_NAME, ())
    provider_id_indexes = indexes.get(FIELD_PROVIDER_ID, ())
    reference_indexes = indexes.get(FIELD_DATE, ())
    age_columns = tuple(
        column for column in policies if column.kind in (FIELD_AGE, FIELD_TEXT)
    )
    maximum_index = max((column.index for column in policies), default=-1)
    patient_namespace = next(
        (column.namespace for column in policies if column.kind == FIELD_PATIENT_ID),
        MRN_NAMESPACE,
    )
    provider_namespace = next(
        (column.namespace for column in policies if column.kind == FIELD_PROVIDER_ID),
        "",
    )
    age_pattern = re.compile(AGE_EXPLICIT_PATTERN)

    def parsed_day(value: str) -> date:
        return parse_date(value).value

    cached_day = lru_cache(maxsize=TABULAR_CACHE_ENTRIES)(parsed_day)

    def day(value: str) -> date:
        return (
            cached_day(value)
            if len(value) <= TABULAR_CACHE_VALUE_CHARACTERS
            else parsed_day(value)
        )

    def extract(values: tuple[str, ...], row_number: int) -> RowEvidence:
        patient_name = _one_value(values, patient_name_indexes)
        patient_id = _one_value(values, patient_id_indexes)
        birth = _one_value(values, birth_indexes)
        references = [
            day(values[index].strip())
            for index in reference_indexes
            if values[index].strip()
        ]
        older_age = False
        for column in policies if maximum_index >= len(values) else age_columns:
            value = values[column.index]
            if column.kind == FIELD_AGE and value.strip():
                if re.fullmatch(r"[0-9]{1,3}\+?", value.strip()) is None:
                    raise ValueError(ERROR_AGE)
                older_age |= int(value.strip().rstrip("+")) >= AGE_GROUP_MINIMUM
            elif column.kind == FIELD_TEXT:
                older_age |= any(
                    int(match["age"]) >= AGE_GROUP_MINIMUM
                    for match in age_pattern.finditer(value)
                    if not value[: match.start()].strip()
                )
        patient = None
        if patient_name or patient_id or birth:
            patient = IdentityEvidence(
                role=IDENTITY_PATIENT,
                name=patient_name,
                identifier=canonical_record_identifier(patient_id, patient_namespace)
                if patient_id
                else "",
                identifier_namespace=patient_namespace,
                birth_date=day(birth.strip()) if birth else None,
                reference_date=max(references) if references else None,
                explicit_older_age=older_age,
                context_key=ROW_CONTEXT_TEMPLATE.format(
                    input_sha256=input_sha256, number=row_number, role=IDENTITY_PATIENT
                ),
            )
        provider_name = _one_value(values, provider_name_indexes)
        provider_id = _one_value(values, provider_id_indexes)
        provider = None
        if provider_name or provider_id:
            provider = IdentityEvidence(
                role=IDENTITY_PROVIDER,
                name=provider_name,
                identifier=normalize_digits(provider_id) if provider_id else "",
                identifier_namespace=provider_namespace,
                context_key=ROW_CONTEXT_TEMPLATE.format(
                    input_sha256=input_sha256, number=row_number, role=IDENTITY_PROVIDER
                ),
            )
        return RowEvidence(patient=patient, provider=provider)

    return extract


def canonical_record_identifier(value: str, namespace: str) -> str:
    if namespace == MRN_NAMESPACE and re.fullmatch(r"[0-9 -]+", value.strip()):
        return normalize_digits(value)
    return value.strip()


def _one_value(values: tuple[str, ...], indexes: tuple[int, ...]) -> str:
    matching = {values[index].strip() for index in indexes}
    matching.discard("")
    if len(matching) > 1:
        raise ValueError(ERROR_IDENTITY_EVIDENCE)
    return next(iter(matching), "")
