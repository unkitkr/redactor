"""Carry edit boundaries into a canonical Unicode view without losing byte checks."""

from unicodedata import normalize

from redactor.schemas.redaction import TextEdit
from redactor.utils.constants import UNICODE_NORMAL_FORM
from redactor.utils.errors import ERROR_REPLACEMENT


def normalized_edits(
    original: str, edits: tuple[TextEdit, ...]
) -> tuple[TextEdit, ...]:
    source_end = normalized_end = 0
    pieces: list[str] = []
    result: list[TextEdit] = []
    for edit in edits:
        prefix = normalize(UNICODE_NORMAL_FORM, original[source_end : edit.start])
        value = normalize(UNICODE_NORMAL_FORM, edit.original)
        pieces.extend((prefix, value))
        start = normalized_end + len(prefix)
        normalized_end = start + len(value)
        result.append(
            edit.model_copy(
                update={
                    "start": start,
                    "end": normalized_end,
                    "original": value,
                    "replacement": normalize(UNICODE_NORMAL_FORM, edit.replacement),
                }
            )
        )
        source_end = edit.end
    pieces.append(normalize(UNICODE_NORMAL_FORM, original[source_end:]))
    if "".join(pieces) != normalize(UNICODE_NORMAL_FORM, original):
        # A composition crossing an edit boundary makes its coverage ambiguous.
        raise ValueError(ERROR_REPLACEMENT)
    return tuple(result)
