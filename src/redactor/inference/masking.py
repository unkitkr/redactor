"""Normalize already assessed spans for caching without losing source positions."""

import re

from redactor.schemas.entities import TextEntity
from redactor.schemas.redaction import TextRange
from redactor.utils.constants import (
    ENTITY_PERSON,
    TEXT_MASK_TOKEN,
    VERIFIER_MENTION_PREFIX_PATTERN,
)
from redactor.utils.errors import ERROR_ENTITY_EVIDENCE


def mask_assessed_ranges(
    text: str, ranges: tuple[TextRange, ...]
) -> tuple[str, tuple[int | None, ...]]:
    merged: list[tuple[int, int]] = []
    for span in sorted(ranges, key=lambda item: (item.start, item.end)):
        if not (0 <= span.start < span.end <= len(text)):
            raise ValueError(ERROR_ENTITY_EVIDENCE)
        if merged and span.start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], span.end))
        else:
            merged.append((span.start, span.end))
    pieces: list[str] = []
    positions: list[int | None] = []
    previous = 0
    for start, end in merged:
        pieces.extend((text[previous:start], TEXT_MASK_TOKEN))
        positions.extend(range(previous, start))
        positions.extend([None] * len(TEXT_MASK_TOKEN))
        previous = end
    pieces.append(text[previous:])
    positions.extend(range(previous, len(text)))
    return "".join(pieces), tuple(positions)


def restore_entity(
    text: str, entity: TextEntity, positions: tuple[int | None, ...]
) -> TextEntity | None:
    selected = positions[entity.start : entity.end]
    source_positions = [position for position in selected if position is not None]
    if not source_positions:
        return None
    if None in selected and entity.entity_type == ENTITY_PERSON:
        masked_start = selected.index(None)
        if all(
            position is None for position in selected[masked_start:]
        ) and re.fullmatch(VERIFIER_MENTION_PREFIX_PATTERN, entity.text[:masked_start]):
            # The only visible characters are a role such as "Dr.". Any extra
            # unmasked name fragment still reaches the strict coverage check.
            return None
    if len(source_positions) != len(selected) or source_positions != list(
        range(source_positions[0], source_positions[-1] + 1)
    ):
        raise ValueError(ERROR_ENTITY_EVIDENCE)
    start, end = source_positions[0], source_positions[-1] + 1
    return entity.model_copy(
        update={"start": start, "end": end, "text": text[start:end]}
    )
