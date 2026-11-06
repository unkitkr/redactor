"""Expose nested JSON strings, typed values, keys and encoded JSON attachments."""

import base64
import binascii
from collections.abc import Iterator

from redactor.formats.json_context import normalized_key, record_evidence
from redactor.formats.json_fields import json_field_policy
from redactor.formats.json_syntax import (
    member,
    member_text,
    object_members,
    parse_json_text,
)
from redactor.schemas.configuration import ResourceSettings
from redactor.schemas.json import JsonNode
from redactor.schemas.native import NativeRecord
from redactor.schemas.redaction import ColumnPolicy, RowEvidence
from redactor.utils.constants import (
    FIELD_IDENTIFIER,
    FIELD_TEXT,
    JSON_BASE64_ENCODING,
    JSON_EMBEDDED_LOCATION,
    JSON_KEY_LOCATION,
    JSON_MEDIA_TYPE,
    JSON_PROVIDER_CONTAINERS,
    JSON_ROOT_LOCATION,
    JSON_VALUE_LOCATION,
    MRN_NAMESPACE,
    TEXT_ENCODING,
)
from redactor.utils.errors import ERROR_COVERAGE, ERROR_STRUCTURE


def attachment_text(node: JsonNode) -> tuple[JsonNode, str] | None:
    data = member(node, "data")
    encoding = member_text(node, "encoding")
    content_type = member_text(node, "content_type") or member_text(node, "contentType")
    if data is None or not (encoding or content_type):
        return None
    if encoding != JSON_BASE64_ENCODING or content_type != JSON_MEDIA_TYPE:
        raise ValueError(ERROR_COVERAGE)
    try:
        decoded = base64.b64decode(data.value, validate=True).decode(TEXT_ENCODING)
    except (binascii.Error, ValueError, UnicodeDecodeError):
        raise ValueError(ERROR_STRUCTURE) from None
    return data, decoded


def json_records(
    node: JsonNode,
    resources: ResourceSettings,
    *,
    location: tuple[str, ...] = JSON_ROOT_LOCATION,
    key: str = "",
    inherited: RowEvidence | None = None,
    provider: bool = False,
    name_part: str = "",
    scope: str = "",
) -> Iterator[NativeRecord]:
    evidence = inherited or RowEvidence(patient=None, provider=None)
    scope = scope or "/".join(location)
    if node.kind == "object":
        context = record_evidence(node, evidence, "/".join(location), provider=provider)
        encoded = attachment_text(node)
        for index, field, value in object_members(node):
            base = (*location, str(index))
            # Standard field names are scanned too; numeric dictionary keys are
            # identifiers even though a text NER model would not recognize them.
            key_policy = ColumnPolicy(index=0, kind=FIELD_TEXT)
            if field.value.isascii() and field.value.isdigit():
                key_policy = ColumnPolicy(
                    index=0, kind=FIELD_IDENTIFIER, namespace=MRN_NAMESPACE
                )
            yield _record(
                field.value, (*base, JSON_KEY_LOCATION), key_policy, context, scope
            )
            child_location = (*base, JSON_VALUE_LOCATION)
            if encoded and value is encoded[0]:
                child = parse_json_text(encoded[1], resources)
                yield from json_records(
                    child,
                    resources,
                    location=(*child_location, JSON_EMBEDDED_LOCATION),
                    inherited=context,
                    provider=provider,
                    scope=scope,
                )
            elif encoded and field.value in ("encoding", "content_type", "contentType"):
                continue  # Validated as exact supported codec constants above.
            else:
                field_name = normalized_key(field.value)
                part = (
                    field_name
                    if key == "name" and field_name in ("given", "family")
                    else ""
                )
                yield from json_records(
                    value,
                    resources,
                    location=child_location,
                    key=field_name,
                    inherited=context,
                    provider=provider or field_name in JSON_PROVIDER_CONTAINERS,
                    name_part=part,
                    scope=scope,
                )
    elif node.kind == "array":
        for index, value in enumerate(node.children):
            child_location = (*location, str(index))
            yield from json_records(
                value,
                resources,
                location=child_location,
                key=key,
                inherited=evidence,
                provider=provider,
                name_part="initial" if name_part == "given" and index else name_part,
                scope="/".join(child_location) if value.kind == "object" else scope,
            )
    elif node.kind in ("string", "number"):
        yield _record(
            node.value,
            location,
            json_field_policy(key, node, provider=provider, name_part=name_part),
            evidence,
            scope,
        )


def _record(
    value: str,
    location: tuple[str, ...],
    policy: ColumnPolicy,
    evidence: RowEvidence,
    scope: str,
) -> NativeRecord:
    return NativeRecord(
        values=(value,),
        locations=(location,),
        policies=(policy,),
        evidence=evidence,
        context_scope=scope,
    )
