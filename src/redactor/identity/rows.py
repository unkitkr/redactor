"""Bind one native row to the accepted identity snapshot."""

from collections.abc import Callable

from redactor.identity.evidence import prepare_observation
from redactor.schemas.identity import (
    IdentityEvidence,
    IdentityLookup,
    IdentityObservation,
)
from redactor.schemas.redaction import RowEvidence, TextContext
from redactor.utils.constants import FIELD_TEXT, ROW_CONTEXT_TEMPLATE


def row_context(
    evidence: RowEvidence,
    lookup: IdentityLookup,
    analysis_task_id: str,
    input_sha256: str,
    row_number: int,
    key: bytes,
    maximum_date_shift_days: int,
    context_scope: str = "",
    *,
    observation_reader: Callable[[IdentityEvidence], IdentityObservation] | None = None,
) -> TextContext:
    patient = evidence.patient
    provider = evidence.provider
    prepare = observation_reader or (lambda item: prepare_observation(item, key))
    return TextContext(
        context_key=f"{input_sha256}:{context_scope}"
        if context_scope
        else ROW_CONTEXT_TEMPLATE.format(
            input_sha256=input_sha256, number=row_number, role=FIELD_TEXT
        ),
        patient_name=patient.name if patient else "",
        provider_name=provider.name if provider else "",
        patient=lookup(
            analysis_task_id,
            prepare(patient).observation_key,
            patient.role,
        )
        if patient
        else None,
        provider=lookup(
            analysis_task_id,
            prepare(provider).observation_key,
            provider.role,
        )
        if provider
        else None,
        maximum_date_shift_days=maximum_date_shift_days,
    )
