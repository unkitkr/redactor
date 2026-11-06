"""Use explicit inherited identity context when a native format supplies it."""

from redactor.identity.tabular import row_evidence
from redactor.policy.name_matching import compatible_name_spelling
from redactor.schemas.identity import IdentityEvidence
from redactor.schemas.native import NativeDocument, NativeRecord
from redactor.schemas.redaction import RowEvidence
from redactor.utils.errors import ERROR_IDENTITY_EVIDENCE


def coalesce_native_context(document: NativeDocument) -> NativeDocument:
    """Complete each explicit record context before any of its fields is analyzed.

    Demographics can live in a nested attachment after the name they describe.
    This joins only adapter-declared contexts, never unrelated people by name.
    """
    people: dict[tuple[str, str], IdentityEvidence] = {}
    for record in document.records:
        if record.evidence is None:
            continue
        for person in (record.evidence.patient, record.evidence.provider):
            if person is None:
                continue
            key = person.role, person.context_key
            old = people.get(key)
            people[key] = _merge_person(old, person) if old else person
    records: list[NativeRecord] = []
    for record in document.records:
        evidence = record.evidence
        if evidence is None:
            records.append(record)
            continue
        records.append(
            record.model_copy(
                update={
                    "evidence": RowEvidence(
                        patient=people[
                            (evidence.patient.role, evidence.patient.context_key)
                        ]
                        if evidence.patient
                        else None,
                        provider=people[
                            (evidence.provider.role, evidence.provider.context_key)
                        ]
                        if evidence.provider
                        else None,
                    )
                }
            )
        )
    return document.model_copy(update={"records": tuple(records)})


def _merge_person(
    first: IdentityEvidence, second: IdentityEvidence
) -> IdentityEvidence:
    if (
        first.name
        and second.name
        and not compatible_name_spelling(first.name, second.name)
    ):
        raise ValueError(ERROR_IDENTITY_EVIDENCE)
    if (
        first.identifier
        and second.identifier
        and (
            (first.identifier, first.identifier_namespace, first.issuer)
            != (second.identifier, second.identifier_namespace, second.issuer)
        )
    ):
        raise ValueError(ERROR_IDENTITY_EVIDENCE)
    if first.birth_date and second.birth_date and first.birth_date != second.birth_date:
        raise ValueError(ERROR_IDENTITY_EVIDENCE)
    reference = max(
        filter(None, (first.reference_date, second.reference_date)), default=None
    )
    name = max((first.name, second.name), key=lambda value: (len(value), value))
    return first.model_copy(
        update={
            "name": name,
            "identifier": first.identifier or second.identifier,
            "identifier_namespace": first.identifier_namespace
            if first.identifier
            else second.identifier_namespace,
            "issuer": first.issuer if first.identifier else second.issuer,
            "birth_date": first.birth_date or second.birth_date,
            "reference_date": reference,
            "explicit_older_age": first.explicit_older_age or second.explicit_older_age,
        }
    )


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
