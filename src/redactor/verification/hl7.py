"""Independently compare every unedited HL7 component and structural delimiter."""

from pathlib import Path

from redactor.formats.hl7_encoding import read_message
from redactor.schemas.native import NativeDocument
from redactor.utils.errors import ERROR_CLINICAL_CHANGED, ERROR_STRUCTURE


def check_hl7_surfaces(
    original: Path, output: Path, document: NativeDocument, encoding: str
) -> None:
    source = read_message(original, encoding)
    saved = read_message(output, encoding)
    if source.model_copy(update={"segments": ()}) != saved.model_copy(
        update={"segments": ()}
    ):
        raise ValueError(ERROR_STRUCTURE)
    if len(source.segments) != len(saved.segments):
        raise ValueError(ERROR_STRUCTURE)
    covered: set[tuple[int, int, int, int]] = set()
    for record in document.records:
        for location in record.locations:
            segment, field, repeat, start, stop = map(int, location[:5])
            covered.update(
                (segment, field, repeat, component) for component in range(start, stop)
            )
    for segment_index, (before, after) in enumerate(
        zip(source.segments, saved.segments, strict=True)
    ):
        if len(before) != len(after) or before[0] != after[0]:
            raise ValueError(ERROR_STRUCTURE)
        for field_index, (left, right) in enumerate(zip(before, after, strict=True)):
            if segment_index == 0 and field_index == 1:
                if left != right:
                    raise ValueError(ERROR_STRUCTURE)
                continue
            left_repeats, right_repeats = (
                left.split(source.repetition),
                right.split(saved.repetition),
            )
            if len(left_repeats) != len(right_repeats):
                raise ValueError(ERROR_STRUCTURE)
            for repeat, (a, b) in enumerate(
                zip(left_repeats, right_repeats, strict=True)
            ):
                first, second = a.split(source.component), b.split(saved.component)
                if len(first) != len(second):
                    raise ValueError(ERROR_STRUCTURE)
                for component, (old, new) in enumerate(zip(first, second, strict=True)):
                    if (
                        segment_index,
                        field_index,
                        repeat,
                        component,
                    ) not in covered and old != new:
                        raise ValueError(ERROR_CLINICAL_CHANGED)
