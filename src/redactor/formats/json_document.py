"""Rewrite only assessed JSON tokens, retaining numeric precision and native types."""

import base64
import json
import re
from pathlib import Path

from redactor.formats.json_records import attachment_text, json_records
from redactor.formats.json_syntax import object_members, parse_json_text
from redactor.identity.native import coalesce_native_context
from redactor.schemas.configuration import ResourceSettings
from redactor.schemas.json import JsonNode
from redactor.schemas.native import NativeDocument
from redactor.utils.constants import (
    JSON_EMBEDDED_LOCATION,
    JSON_KEY_LOCATION,
    JSON_NUMBER_PATTERN,
    JSON_ROOT_LOCATION,
    JSON_VALUE_LOCATION,
    TEXT_ENCODING,
    UTF8_BOM_ENCODING,
)
from redactor.utils.errors import ERROR_COVERAGE, ERROR_STRUCTURE


def read_json_document(
    path: Path, resources: ResourceSettings, *, extract_evidence: bool = True
) -> NativeDocument:
    text = path.read_text(encoding=UTF8_BOM_ENCODING)
    node = parse_json_text(text, resources)
    document = NativeDocument(
        records=tuple(json_records(node, resources, extract_evidence=extract_evidence))
    )
    return coalesce_native_context(document) if extract_evidence else document


def write_json_document(
    original: Path,
    output: Path,
    replacements: dict[tuple[str, ...], str],
    resources: ResourceSettings,
) -> None:
    text = original.read_bytes().decode(TEXT_ENCODING)
    bom = "\ufeff" if text.startswith("\ufeff") else ""
    used: set[tuple[str, ...]] = set()
    rewritten = rewrite_json_text(text.removeprefix(bom), replacements, resources, used)
    if used != set(replacements):
        raise ValueError(ERROR_COVERAGE)
    output.write_bytes((bom + rewritten).encode(TEXT_ENCODING))


def rewrite_json_text(
    text: str,
    replacements: dict[tuple[str, ...], str],
    resources: ResourceSettings,
    used: set[tuple[str, ...]],
    location: tuple[str, ...] = JSON_ROOT_LOCATION,
) -> str:
    root = parse_json_text(text, resources)
    edits: list[tuple[int, int, str]] = []

    def visit(node: JsonNode, path: tuple[str, ...]) -> None:
        if path in replacements:
            value = replacements[path]
            if node.kind == "string":
                encoded = json.dumps(value, ensure_ascii=False)
            elif node.kind == "number" and re.fullmatch(JSON_NUMBER_PATTERN, value):
                encoded = value
            else:
                raise ValueError(ERROR_STRUCTURE)
            edits.append((node.start, node.end, encoded))
            used.add(path)
        elif node.kind == "array":
            for index, child in enumerate(node.children):
                visit(child, (*path, str(index)))
        elif node.kind == "object":
            attachment = attachment_text(node)
            for index, key, child in object_members(node):
                base = (*path, str(index))
                visit(key, (*base, JSON_KEY_LOCATION))
                child_path = (*base, JSON_VALUE_LOCATION)
                if attachment and child is attachment[0]:
                    decoded = rewrite_json_text(
                        attachment[1],
                        replacements,
                        resources,
                        used,
                        (*child_path, JSON_EMBEDDED_LOCATION),
                    )
                    encoded = base64.b64encode(decoded.encode(TEXT_ENCODING)).decode(
                        "ascii"
                    )
                    edits.append((child.start, child.end, json.dumps(encoded)))
                else:
                    visit(child, child_path)

    visit(root, location)
    pieces: list[str] = []
    cursor = 0
    for start, end, replacement in sorted(edits):
        if start < cursor:
            raise ValueError(ERROR_COVERAGE)
        pieces.extend((text[cursor:start], replacement))
        cursor = end
    pieces.append(text[cursor:])
    result = "".join(pieces)
    parse_json_text(result, resources)  # Reject key collisions and malformed output.
    return result
