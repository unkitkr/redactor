"""Use explicit inherited identity context when a native format supplies it."""

from redactor.identity.tabular import row_evidence
from redactor.schemas.native import NativeRecord
from redactor.schemas.redaction import RowEvidence


def native_evidence(
    record: NativeRecord, input_sha256: str, number: int
) -> RowEvidence:
    if record.evidence is None:
        return row_evidence(record.values, record.policies, input_sha256, number)
    return RowEvidence(
        patient=record.evidence.patient.model_copy(
            update={
                "context_key": f"{input_sha256}:{record.evidence.patient.context_key}"
            }
        )
        if record.evidence.patient
        else None,
        provider=record.evidence.provider.model_copy(
            update={
                "context_key": f"{input_sha256}:{record.evidence.provider.context_key}"
            }
        )
        if record.evidence.provider
        else None,
    )
