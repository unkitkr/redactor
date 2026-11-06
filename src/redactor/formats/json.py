"""Validate complete JSON streams with bounded tokens and duplicate-key checks."""

from collections.abc import Generator
from pathlib import Path

import ijson  # type: ignore[import-untyped]  # Upstream has no typing marker.

from redactor.schemas.configuration import ResourceSettings
from redactor.schemas.formats import FileFormat
from redactor.utils.constants import (
    FHIR_BUNDLE_TYPE,
    FORMAT_FHIR,
    FORMAT_JSON,
    JSON_END_ARRAY,
    JSON_END_MAP,
    JSON_MAP_KEY,
    JSON_RESOURCE_TYPE,
    JSON_SCALAR_DELIMITERS,
    JSON_START_ARRAY,
    JSON_START_MAP,
    JSON_STRING,
    UTF8_BOM,
)
from redactor.utils.errors import ERROR_RESOURCE_LIMIT, ERROR_STRUCTURE


def inspect_json(path: Path, resources: ResourceSettings) -> tuple[FileFormat, int]:
    is_fhir_bundle = False
    scalar_count = 0

    def consume_events() -> Generator[None, tuple[str, object], None]:
        nonlocal is_fhir_bundle, scalar_count
        containers: list[set[str] | None] = []
        active_key_bytes = 0
        root_key = ""
        root_started = False
        while True:
            event, value = yield
            if not root_started:
                if event not in (JSON_START_MAP, JSON_START_ARRAY):
                    raise ValueError(ERROR_STRUCTURE)
                root_started = True
            if event in (JSON_START_MAP, JSON_START_ARRAY):
                containers.append(set() if event == JSON_START_MAP else None)
                if len(containers) > resources.max_nesting_depth:
                    raise ValueError(ERROR_RESOURCE_LIMIT)
            elif event in (JSON_END_MAP, JSON_END_ARRAY):
                keys = containers.pop()
                if keys is not None:
                    active_key_bytes -= sum(len(key.encode()) for key in keys)
            elif event == JSON_MAP_KEY:
                keys = containers[-1]
                if not isinstance(value, str) or keys is None or value in keys:
                    raise ValueError(ERROR_STRUCTURE)
                keys.add(value)
                active_key_bytes += len(value.encode())
                if active_key_bytes > resources.max_record_bytes:
                    raise ValueError(ERROR_RESOURCE_LIMIT)
                if len(containers) == 1:
                    root_key = value
            else:
                scalar_count += 1
                if (
                    len(containers) == 1
                    and root_key == JSON_RESOURCE_TYPE
                    and event == JSON_STRING
                    and value == FHIR_BUNDLE_TYPE
                ):
                    is_fhir_bundle = True

    consumer = consume_events()
    next(consumer)
    parser = ijson.basic_parse_coro(consumer)
    try:
        for chunk in _bounded_json_chunks(path, resources):
            parser.send(chunk)
        parser.close()  # Reject unfinished final strings, numbers, or containers.
    except ijson.JSONError:
        raise ValueError(ERROR_STRUCTURE) from None
    finally:
        consumer.close()
    return (FORMAT_FHIR if is_fhir_bundle else FORMAT_JSON), scalar_count


def _bounded_json_chunks(
    path: Path, resources: ResourceSettings
) -> Generator[bytes, None, None]:
    """Reject oversized tokens before the parser can allocate their full value."""
    in_string = False
    escaped = False
    token_bytes = 0
    with path.open("rb") as stream:
        if stream.read(len(UTF8_BOM)) != UTF8_BOM:
            stream.seek(0)
        while chunk := stream.read(resources.chunk_bytes):
            for byte in chunk:
                if in_string:
                    token_bytes += 1
                    if escaped:
                        escaped = False
                    elif byte == ord("\\"):
                        escaped = True
                    elif byte == ord('"'):
                        in_string = False
                        token_bytes = 0
                elif byte == ord('"'):
                    in_string = True
                    token_bytes = 0
                elif byte in JSON_SCALAR_DELIMITERS:
                    token_bytes = 0
                else:
                    token_bytes += 1
                if token_bytes > resources.max_record_bytes:
                    raise ValueError(ERROR_RESOURCE_LIMIT)
            yield chunk
