"""Check exact edit locations and rescan unexempted serialized text."""

import re

from redactor.inference.evidence import validate_entity_evidence
from redactor.inference.masking import mask_assessed_ranges, restore_entity
from redactor.policy.text_patterns import age_mentions, clinical_ranges
from redactor.schemas.entities import NerAdapter, TextEntities
from redactor.schemas.redaction import TextEdit, TextRange
from redactor.utils.constants import AGE_GROUP_MINIMUM, VERIFIER_RESIDUAL_PATTERNS
from redactor.utils.errors import (
    ERROR_CLINICAL_CHANGED,
    ERROR_REPLACEMENT,
    ERROR_RESIDUAL_PHI,
)


def verify_text_changes(
    original: str,
    output: str,
    expected: tuple[TextEdit, ...],
    local_ner: NerAdapter,
    *,
    free_text: bool,
) -> None:
    """An exemption belongs to one span, never every occurrence of its value."""
    source_end = output_end = 0
    source_ranges: list[TextRange] = []
    output_ranges: list[TextRange] = []
    clinical = clinical_ranges(original) if free_text else ()
    for edit in expected:
        if (
            edit.start < source_end
            or original[edit.start : edit.end] != edit.original
            or edit.original == edit.replacement
        ):
            raise ValueError(ERROR_REPLACEMENT)
        unchanged = original[source_end : edit.start]
        if output[output_end : output_end + len(unchanged)] != unchanged:
            raise ValueError(ERROR_CLINICAL_CHANGED)
        output_start = output_end + len(unchanged)
        output_end = output_start + len(edit.replacement)
        if output[output_start:output_end] != edit.replacement:
            raise ValueError(ERROR_REPLACEMENT)
        if any(edit.start < span.end and edit.end > span.start for span in clinical):
            raise ValueError(ERROR_CLINICAL_CHANGED)
        source_ranges.append(TextRange(start=edit.start, end=edit.end))
        output_ranges.append(TextRange(start=output_start, end=output_end))
        source_end = edit.end
    if output[output_end:] != original[source_end:]:
        raise ValueError(ERROR_CLINICAL_CHANGED)
    if free_text:
        # The source scan detects patterns the writer missed. The output scan
        # separately detects residuals and allows only the confirmed edit spans.
        scan_residuals(original, tuple(source_ranges), local_ner)
        scan_residuals(output, tuple(output_ranges), local_ner)


def scan_residuals(
    text: str, exemptions: tuple[TextRange, ...], local_ner: NerAdapter
) -> None:
    for pattern in VERIFIER_RESIDUAL_PATTERNS:
        for match in re.finditer(pattern, text):
            if not any(
                match.start() < span.end and match.end() > span.start
                for span in exemptions
            ):
                raise ValueError(ERROR_RESIDUAL_PHI)
    ages = age_mentions(text)
    for _, number, age in ages:
        if age == AGE_GROUP_MINIMUM and text[number.end : number.end + 1] == "+":
            continue
        if age >= AGE_GROUP_MINIMUM and not any(
            span.start <= number.start and span.end >= number.end for span in exemptions
        ):
            raise ValueError(ERROR_RESIDUAL_PHI)
    allowed = (
        exemptions
        + clinical_ranges(text)
        + tuple(expression for expression, _, _ in ages)
    )
    masked, positions = mask_assessed_ranges(text, allowed)
    entities = validate_entity_evidence(
        masked, TextEntities(entities=local_ner(masked))
    )
    if any(restore_entity(text, entity, positions) is not None for entity in entities):
        raise ValueError(ERROR_RESIDUAL_PHI)
