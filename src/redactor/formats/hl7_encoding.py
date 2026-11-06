"""Parse declared HL7 separators and escape literal delimiter characters."""

import re
from pathlib import Path

from redactor.schemas.hl7 import Hl7Message
from redactor.utils.constants import (
    HL7_ESCAPE_CODES,
    HL7_NAME_MODE,
    HL7_PHONE_MODE,
    HL7_SEGMENT_ENDINGS,
)
from redactor.utils.errors import ERROR_COVERAGE, ERROR_STRUCTURE


def read_message(path: Path, encoding: str) -> Hl7Message:
    with path.open(encoding=encoding, newline="") as stream:
        text = stream.read()
    if len(text) < 9 or not text.startswith("MSH"):
        raise ValueError(ERROR_STRUCTURE)
    separators = text[3:8]
    if len(set(separators)) != 5 or any(c.isalnum() or c.isspace() for c in separators):
        raise ValueError(ERROR_STRUCTURE)
    if text[8] != separators[0]:
        raise ValueError(ERROR_COVERAGE)
    parts = re.split(HL7_SEGMENT_ENDINGS, text)
    segments: list[tuple[str, ...]] = []
    endings: list[str] = []
    for index in range(0, len(parts), 2):
        if not parts[index] and index == len(parts) - 1:
            break
        segment = tuple(parts[index].split(separators[0]))
        if re.fullmatch(r"[A-Z][A-Z0-9]{2}", segment[0]) is None:
            raise ValueError(ERROR_STRUCTURE)
        segments.append(segment)
        endings.append(parts[index + 1] if index + 1 < len(parts) else "")
    if sum(segment[0] == "PID" for segment in segments) != 1:
        raise ValueError(ERROR_COVERAGE)
    if sum(segment[0] == "MSH" for segment in segments) != 1:
        raise ValueError(ERROR_COVERAGE)
    return Hl7Message(
        field=separators[0],
        component=separators[1],
        repetition=separators[2],
        escape=separators[3],
        subcomponent=separators[4],
        segments=tuple(segments),
        endings=tuple(endings),
    )


def decode_component(value: str, message: Hl7Message) -> str:
    escapes = dict(
        zip(
            HL7_ESCAPE_CODES,
            (
                message.field,
                message.component,
                message.repetition,
                message.escape,
                message.subcomponent,
            ),
            strict=True,
        )
    )
    pieces = value.split(message.escape)
    if len(pieces) % 2 == 0:
        raise ValueError(ERROR_STRUCTURE)
    for index in range(1, len(pieces), 2):
        if pieces[index] not in escapes:
            raise ValueError(ERROR_COVERAGE)
        pieces[index] = escapes[pieces[index]]
    if message.subcomponent in value:
        raise ValueError(ERROR_COVERAGE)
    return "".join(pieces)


def encode_component(value: str, message: Hl7Message) -> str:
    escapes = dict(
        zip(
            (
                message.field,
                message.component,
                message.repetition,
                message.escape,
                message.subcomponent,
            ),
            HL7_ESCAPE_CODES,
            strict=True,
        )
    )
    if "\r" in value or "\n" in value:
        raise ValueError(ERROR_STRUCTURE)
    return "".join(
        message.escape + escapes[character] + message.escape
        if character in escapes
        else character
        for character in value
    )


def write_hl7(
    original: Path,
    output: Path,
    replacements: dict[tuple[str, ...], str],
    encoding: str,
) -> None:
    message = read_message(original, encoding)
    fields = [list(segment) for segment in message.segments]
    for location, value in replacements.items():
        segment, field, repeat, start, stop = map(int, location[:5])
        repetitions = fields[segment][field].split(message.repetition)
        components = repetitions[repeat].split(message.component)
        mode = location[5]
        if mode == HL7_NAME_MODE:
            changed = value.split("^")
        elif mode == HL7_PHONE_MODE:
            country_length = len(components[start])
            changed = [
                value[:country_length],
                value[country_length : country_length + 3],
                value[country_length + 3 :],
            ]
        else:
            changed = [value]
        if len(changed) != stop - start:
            raise ValueError(ERROR_STRUCTURE)
        components[start:stop] = [encode_component(item, message) for item in changed]
        repetitions[repeat] = message.component.join(components)
        fields[segment][field] = message.repetition.join(repetitions)
    with output.open("w", encoding=encoding, newline="") as stream:
        for segment_values, ending in zip(fields, message.endings, strict=True):
            stream.write(message.field.join(segment_values) + ending)
