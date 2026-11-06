"""Locate JSON scalars without rounding numbers or regenerating untouched bytes."""

import json
import re
from collections.abc import Iterator

from redactor.schemas.configuration import ResourceSettings
from redactor.schemas.json import JsonNode
from redactor.utils.constants import JSON_NUMBER_PATTERN
from redactor.utils.errors import ERROR_RESOURCE_LIMIT, ERROR_STRUCTURE


def parse_json_text(text: str, resources: ResourceSettings) -> JsonNode:
    decoder = json.JSONDecoder()

    def whitespace(position: int) -> int:
        while position < len(text) and text[position] in " \r\n\t":
            position += 1
        return position

    def parse(position: int, depth: int) -> JsonNode:
        if depth > resources.max_nesting_depth:
            raise ValueError(ERROR_RESOURCE_LIMIT)
        start = whitespace(position)
        if start == len(text):
            raise ValueError(ERROR_STRUCTURE)
        character = text[start]
        if character in "[{":
            is_object = character == "{"
            closing = "}" if is_object else "]"
            children: list[JsonNode] = []
            keys: set[str] = set()
            position = whitespace(start + 1)
            if position < len(text) and text[position] == closing:
                return JsonNode(
                    kind="object" if is_object else "array",
                    start=start,
                    end=position + 1,
                )
            while position < len(text):
                if is_object:
                    key = parse(position, depth + 1)
                    position = whitespace(key.end)
                    if (
                        key.kind != "string"
                        or key.value in keys
                        or text[position : position + 1] != ":"
                    ):
                        raise ValueError(ERROR_STRUCTURE)
                    children.append(key)
                    keys.add(key.value)
                    position += 1
                child = parse(position, depth + 1)
                children.append(child)
                position = whitespace(child.end)
                if text[position : position + 1] == closing:
                    return JsonNode(
                        kind="object" if is_object else "array",
                        start=start,
                        end=position + 1,
                        children=tuple(children),
                    )
                if text[position : position + 1] != ",":
                    raise ValueError(ERROR_STRUCTURE)
                position = whitespace(position + 1)
            raise ValueError(ERROR_STRUCTURE)
        try:
            value, end = decoder.raw_decode(text, start)
        except json.JSONDecodeError:
            raise ValueError(ERROR_STRUCTURE) from None
        raw = text[start:end]
        if len(raw.encode()) > resources.max_record_bytes:
            raise ValueError(ERROR_RESOURCE_LIMIT)
        if isinstance(value, str):
            value.encode("utf-8", errors="strict")
            return JsonNode(kind="string", start=start, end=end, value=value)
        if raw in ("true", "false", "null"):
            return JsonNode(
                kind="null" if raw == "null" else "boolean",
                start=start,
                end=end,
                value=raw,
            )
        if re.fullmatch(JSON_NUMBER_PATTERN, raw) is None:
            raise ValueError(ERROR_STRUCTURE)
        return JsonNode(kind="number", start=start, end=end, value=raw)

    root = parse(0, 0)
    if whitespace(root.end) != len(text) or root.kind not in ("object", "array"):
        raise ValueError(ERROR_STRUCTURE)
    return root


def object_members(node: JsonNode) -> Iterator[tuple[int, JsonNode, JsonNode]]:
    if node.kind == "object":
        for index in range(0, len(node.children), 2):
            yield index // 2, node.children[index], node.children[index + 1]


def member(node: JsonNode, key: str) -> JsonNode | None:
    return next(
        (value for _, name, value in object_members(node) if name.value == key), None
    )


def member_text(node: JsonNode, key: str) -> str:
    value = member(node, key)
    return value.value if value is not None and not value.children else ""
