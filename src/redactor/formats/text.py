"""Expose labelled fields and narrative gaps without changing text encoding."""

import re
from pathlib import Path
from typing import cast

from redactor.schemas.native import NativeDocument, NativeRecord
from redactor.schemas.redaction import ColumnPolicy, FieldKind
from redactor.utils.constants import FIELD_TEXT, TEXT_LABEL_FIELDS, TEXT_PART
from redactor.utils.errors import ERROR_COVERAGE


def text_segments(text: str) -> tuple[tuple[int, int, FieldKind, str], ...]:
    fields: list[tuple[int, int, FieldKind, str]] = []
    for pattern, kind, namespace in TEXT_LABEL_FIELDS:
        for match in re.finditer(pattern, text):
            start, end = match.span("value")
            fields.append((start, end, cast(FieldKind, kind), namespace))
    ordered = sorted(fields)
    segments: list[tuple[int, int, FieldKind, str]] = []
    previous = 0
    for start, end, kind, namespace in ordered:
        if start < previous:
            raise ValueError(ERROR_COVERAGE)
        if start > previous:
            segments.append((previous, start, FIELD_TEXT, ""))
        segments.append((start, end, kind, namespace))
        previous = end
    if previous < len(text):
        segments.append((previous, len(text), FIELD_TEXT, ""))
    return tuple(segments)


def text_record(text: str, part: str = TEXT_PART) -> NativeRecord:
    segments = text_segments(text)
    return NativeRecord(
        values=tuple(text[start:end] for start, end, _, _ in segments),
        policies=tuple(
            ColumnPolicy(index=index, kind=kind, namespace=namespace)
            for index, (_, _, kind, namespace) in enumerate(segments)
        ),
        locations=tuple((part, str(index)) for index in range(len(segments))),
    )


def read_text(path: Path, encoding: str) -> NativeDocument:
    # The native dispatcher bounds the file before this allocation.
    with path.open(encoding=encoding, newline="") as stream:
        text = stream.read()
    return NativeDocument(records=(text_record(text),))


def replace_text_fields(
    text: str, replacements: dict[tuple[str, ...], str], part: str = TEXT_PART
) -> str:
    return "".join(
        replacements.get((part, str(index)), text[start:end])
        for index, (start, end, _, _) in enumerate(text_segments(text))
    )


def write_text(
    original: Path,
    output: Path,
    replacements: dict[tuple[str, ...], str],
    encoding: str,
) -> None:
    with original.open(encoding=encoding, newline="") as stream:
        text = stream.read()
    with output.open("w", encoding=encoding, newline="") as stream:
        stream.write(replace_text_fields(text, replacements))
