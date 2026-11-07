"""Keep patient-shifted date columns out of context-free replacement caches."""

import hashlib

from redactor.identity.cohorts import resolve_cohort
from redactor.policy.dates import shift_date
from redactor.policy.tabular_runtime import typed_column_operations
from redactor.schemas.identity import IdentityCohort, IdentityMatch, ResolvedIdentity
from redactor.schemas.redaction import ColumnPolicy, TextContext
from redactor.utils.constants import (
    CONTEXT_FREE_FIELD_KINDS,
    DEFAULT_DATE_SHIFT_DAYS,
    FIELD_BIRTH_DATE,
    FIELD_DATE,
    FIELD_TEXT,
    ROW_CONTEXT_TEMPLATE,
)


def _resolved_patient(
    identity_label: str, anchor_name: str, key: bytes
) -> ResolvedIdentity:
    identity_key = hashlib.sha256(identity_label.encode()).hexdigest()
    return resolve_cohort(
        IdentityCohort(identity_key=identity_key, anchor_name=anchor_name),
        IdentityMatch(identity_key=identity_key, status="corroborated"),
        key,
        DEFAULT_DATE_SHIFT_DAYS,
    )


def _row_context(number: int, patient: ResolvedIdentity) -> TextContext:
    return TextContext(
        context_key=ROW_CONTEXT_TEMPLATE.format(
            input_sha256="a" * 64, number=number, role=FIELD_TEXT
        ),
        patient=patient,
        maximum_date_shift_days=DEFAULT_DATE_SHIFT_DAYS,
    )


def test_date_replacements_follow_patient_offsets_not_shared_caches() -> None:
    # Dates shift by the patient identity offset, so a context-dependent kind
    # here would let two patients share one cached replacement while
    # publication still passed with wrong dates.
    assert FIELD_DATE not in CONTEXT_FREE_FIELD_KINDS
    assert FIELD_BIRTH_DATE not in CONTEXT_FREE_FIELD_KINDS

    key = bytes(range(32))
    policy = ColumnPolicy(index=0, kind="date")
    assess, replace = typed_column_operations(policy, key)
    date_value = "2026-04-05"

    first_patient = _resolved_patient("tabular-runtime-patient-a", "Alice Stone", key)
    second_patient = _resolved_patient(
        "tabular-runtime-patient-b", "Brendan Quinn", key
    )
    assert first_patient.date_offset_days != second_patient.date_offset_days

    first_context = _row_context(1, first_patient)
    second_context = _row_context(2, second_patient)

    assert assess(date_value)
    first_replacement = replace(date_value, first_context)
    second_replacement = replace(date_value, second_context)
    assert first_replacement == shift_date(date_value, first_patient.date_offset_days)
    assert second_replacement == shift_date(date_value, second_patient.date_offset_days)
    assert first_replacement != second_replacement
    # Repeating one context, even interleaved with another patient, stays exact.
    assert replace(date_value, second_context) == second_replacement
    assert replace(date_value, first_context) == first_replacement
