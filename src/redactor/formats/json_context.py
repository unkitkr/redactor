"""Inherit clinical record context without joining unrelated nested people."""

import re

from redactor.formats.json_syntax import member, member_text, object_members
from redactor.formats.tabular_fields import column_policies
from redactor.identity.tabular import row_evidence
from redactor.schemas.json import JsonNode
from redactor.schemas.redaction import ColumnPolicy, RowEvidence
from redactor.utils.constants import (
    FIELD_BIRTH_DATE,
    FIELD_DATE,
    FIELD_PATIENT_ID,
    FIELD_PATIENT_NAME,
    FIELD_PROVIDER_ID,
    FIELD_PROVIDER_NAME,
    JSON_DATE_KEYS,
    JSON_PATIENT_CONTAINERS,
    JSON_PROVIDER_CONTAINERS,
)


def normalized_key(key: str) -> str:
    separated = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", key)
    return re.sub(r"[\s-]+", "_", separated).casefold()


def human_name(node: JsonNode | None) -> str:
    if node is None:
        return ""
    if node.kind == "string":
        return node.value
    if node.kind == "object":
        given = member(node, "given")
        names = tuple(value.value for value in given.children) if given else ()
        family = member_text(node, "family")
        return " ".join((*names, family)).strip()
    return ""


def record_evidence(
    node: JsonNode, inherited: RowEvidence, scope: str, *, provider: bool = False
) -> RowEvidence:
    """A child may add dates, but another named person starts a distinct record."""
    values: list[str] = []
    policies: list[ColumnPolicy] = []

    def field(value: str, policy: ColumnPolicy) -> None:
        if value:
            policies.append(policy.model_copy(update={"index": len(values)}))
            values.append(value)

    def person(person_node: JsonNode, is_provider: bool) -> None:
        name = human_name(member(person_node, "name"))
        field(
            name,
            ColumnPolicy(
                index=0, kind=FIELD_PROVIDER_NAME if is_provider else FIELD_PATIENT_NAME
            ),
        )
        for _, key, value in object_members(person_node):
            normalized = normalized_key(key.value)
            policy = column_policies((normalized,))[0]
            if normalized in JSON_DATE_KEYS:
                field(value.value, ColumnPolicy(index=0, kind=FIELD_DATE))
            elif normalized in ("dob", "birth_date", "birthdate") and not is_provider:
                field(value.value, ColumnPolicy(index=0, kind=FIELD_BIRTH_DATE))
            elif policy.kind in (FIELD_PATIENT_ID, FIELD_PROVIDER_ID):
                field(value.value, policy)
            elif normalized in ("member_id", "subscriber_id") and not is_provider:
                field(
                    value.value,
                    ColumnPolicy(index=0, kind=FIELD_PATIENT_ID, namespace=normalized),
                )

    person(node, provider)
    for _, key, child in object_members(node):
        if normalized_key(key.value) in JSON_PATIENT_CONTAINERS:
            person(child, False)
        elif normalized_key(key.value) in JSON_PROVIDER_CONTAINERS:
            person(child, True)
    current = row_evidence(tuple(values), tuple(policies), scope, 0)

    def inherit(is_provider: bool) -> None:
        nonlocal current
        old = inherited.provider if is_provider else inherited.patient
        new = current.provider if is_provider else current.patient
        if (
            new
            and old
            and (not new.name or new.name == old.name)
            and (not new.identifier or new.identifier == old.identifier)
        ):
            new = new.model_copy(
                update={
                    "name": new.name or old.name,
                    "identifier": new.identifier or old.identifier,
                    "identifier_namespace": new.identifier_namespace
                    if new.identifier
                    else old.identifier_namespace,
                    "birth_date": new.birth_date or old.birth_date,
                    "reference_date": max(
                        filter(None, (new.reference_date, old.reference_date)),
                        default=None,
                    ),
                    "context_key": old.context_key,
                }
            )
        elif new:
            new = new.model_copy(update={"context_key": scope})
        current = current.model_copy(
            update={"provider" if is_provider else "patient": new or old}
        )

    inherit(False)
    inherit(True)
    return current
