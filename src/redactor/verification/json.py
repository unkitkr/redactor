"""Independently parse saved JSON and account for every changed native token."""

import json
from decimal import Decimal
from pathlib import Path

from redactor.formats.json_records import attachment_text
from redactor.formats.json_syntax import object_members, parse_json_text
from redactor.schemas.configuration import ResourceSettings
from redactor.schemas.json import JsonNode
from redactor.schemas.native import NativeDocument
from redactor.utils.constants import (
    JSON_EMBEDDED_LOCATION,
    JSON_KEY_LOCATION,
    JSON_ROOT_LOCATION,
    JSON_VALUE_LOCATION,
    UTF8_BOM_ENCODING,
)
from redactor.utils.errors import ERROR_COVERAGE, ERROR_STRUCTURE


def check_json_surfaces(
    original: Path, output: Path, document: NativeDocument, resources: ResourceSettings
) -> None:
    before = original.read_text(encoding=UTF8_BOM_ENCODING)
    after = output.read_text(encoding=UTF8_BOM_ENCODING)
    # The standard library is a separate syntax/number parser from the writer.
    json.loads(after, parse_float=Decimal, parse_constant=_reject_constant)
    locations = {
        location for record in document.records for location in record.locations
    }
    _check_nodes(
        parse_json_text(before, resources),
        parse_json_text(after, resources),
        locations,
        JSON_ROOT_LOCATION,
        resources,
    )


def _check_nodes(
    before: JsonNode,
    after: JsonNode,
    locations: set[tuple[str, ...]],
    path: tuple[str, ...],
    resources: ResourceSettings,
) -> None:
    if before.kind != after.kind or len(before.children) != len(after.children):
        raise ValueError(ERROR_STRUCTURE)
    if before.kind == "object":
        source_attachment = attachment_text(before)
        saved_attachment = attachment_text(after)
        if bool(source_attachment) != bool(saved_attachment):
            raise ValueError(ERROR_COVERAGE)
        for (index, key, value), (_, saved_key, saved_value) in zip(
            object_members(before), object_members(after), strict=True
        ):
            base = (*path, str(index))
            _check_nodes(
                key, saved_key, locations, (*base, JSON_KEY_LOCATION), resources
            )
            location = (*base, JSON_VALUE_LOCATION)
            if source_attachment and value is source_attachment[0]:
                if saved_attachment is None or saved_value is not saved_attachment[0]:
                    raise ValueError(ERROR_COVERAGE)
                json.loads(
                    saved_attachment[1],
                    parse_float=Decimal,
                    parse_constant=_reject_constant,
                )
                _check_nodes(
                    parse_json_text(source_attachment[1], resources),
                    parse_json_text(saved_attachment[1], resources),
                    locations,
                    (*location, JSON_EMBEDDED_LOCATION),
                    resources,
                )
            else:
                _check_nodes(value, saved_value, locations, location, resources)
    elif before.kind == "array":
        for index, (source, saved) in enumerate(
            zip(before.children, after.children, strict=True)
        ):
            _check_nodes(source, saved, locations, (*path, str(index)), resources)
    elif path not in locations and before.value != after.value:
        raise ValueError(ERROR_COVERAGE)


def _reject_constant(_value: str) -> None:
    raise ValueError(ERROR_STRUCTURE)
