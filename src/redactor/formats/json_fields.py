"""Interpret JSON field semantics before falling back to contextual text analysis."""

from redactor.formats.json_context import normalized_key
from redactor.formats.tabular_fields import column_policies
from redactor.schemas.json import JsonNode
from redactor.schemas.redaction import ColumnPolicy
from redactor.utils.constants import (
    FIELD_BIRTH_DATE,
    FIELD_CLINICAL,
    FIELD_DATE,
    FIELD_IDENTIFIER,
    FIELD_LOCATION,
    FIELD_PATIENT_ID,
    FIELD_PATIENT_NAME,
    FIELD_PROVIDER_NAME,
    FIELD_TEXT,
    JSON_DATE_KEYS,
    JSON_FIELD_ALIASES,
    JSON_IDENTIFIER_KEYS,
    JSON_QUANTITY_KEYS,
)


def json_field_policy(
    key: str, node: JsonNode, *, provider: bool, name_part: str = ""
) -> ColumnPolicy:
    normalized = normalized_key(key)
    normalized = dict(JSON_FIELD_ALIASES).get(normalized, normalized)
    policy = column_policies((normalized,))[0]
    if normalized == "name" or name_part in ("family", "given", "initial"):
        policy = ColumnPolicy(
            index=0,
            kind=FIELD_PROVIDER_NAME if provider else FIELD_PATIENT_NAME,
            name_part=name_part,
        )
    elif normalized in ("member_id", "subscriber_id"):
        policy = ColumnPolicy(index=0, kind=FIELD_PATIENT_ID, namespace=normalized)
    elif normalized in JSON_IDENTIFIER_KEYS:
        policy = ColumnPolicy(index=0, kind=FIELD_IDENTIFIER, namespace=normalized)
    elif normalized in JSON_QUANTITY_KEYS or (
        normalized == "units" and node.kind == "number"
    ):
        policy = ColumnPolicy(index=0, kind=FIELD_CLINICAL, namespace="quantity")
    elif policy.kind != FIELD_BIRTH_DATE and (
        normalized in JSON_DATE_KEYS or normalized.endswith("_date")
    ):
        policy = ColumnPolicy(index=0, kind=FIELD_DATE)
    elif normalized == "city":
        policy = ColumnPolicy(index=0, kind=FIELD_LOCATION)
    elif normalized == "state":
        policy = ColumnPolicy(index=0, kind=FIELD_CLINICAL, namespace="state")
    elif policy.kind == FIELD_TEXT and node.kind == "number":
        policy = ColumnPolicy(index=0, kind=FIELD_CLINICAL, namespace="quantity")
    return policy.model_copy(update={"numeric": node.kind == "number"})
