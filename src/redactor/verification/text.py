"""Check exact edit locations and rescan serialized text without hiding context."""

from unicodedata import normalize

from redactor.schemas.entities import NerAdapter
from redactor.schemas.redaction import TextEdit, TextRange
from redactor.utils.constants import UNICODE_NORMAL_FORM
from redactor.utils.errors import (
    ERROR_CLINICAL_CHANGED,
    ERROR_REPLACEMENT,
)
from redactor.verification.normalization import normalized_edits
from redactor.verification.residuals import (
    assessed_age_ranges,
    protected_clinical_ranges,
)
from redactor.verification.residuals import scan_residuals as scan_residuals


def verify_text_changes(
    original: str,
    output: str,
    expected: tuple[TextEdit, ...],
    local_ner: NerAdapter,
    *,
    free_text: bool,
    patient_name: str = "",
    provider_name: str = "",
) -> None:
    """An exemption belongs to one span, never every occurrence of its value."""
    source_end = output_end = 0
    source_ranges: list[TextRange] = []
    output_ranges: list[TextRange] = []
    clinical = protected_clinical_ranges(original) if free_text else ()
    for edit in expected:
        if (
            not (source_end <= edit.start < edit.end <= len(original))
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
        scan_residuals(
            original,
            tuple(source_ranges),
            local_ner,
            patient_name=patient_name,
            provider_name=provider_name,
            clinical=clinical,
        )
        age_ranges = assessed_age_ranges(original)
        scan_residuals(
            output,
            tuple(output_ranges),
            local_ner,
            patient_name=patient_name,
            provider_name=provider_name,
            clinical=_output_ranges(clinical, expected),
            assessed_ages=_output_ranges(age_ranges, expected),
        )
        canonical_original = normalize(UNICODE_NORMAL_FORM, original)
        canonical_output = normalize(UNICODE_NORMAL_FORM, output)
        if canonical_original != original or canonical_output != output:
            # Normalization is an extra read-only view. Exact serialized gaps,
            # raw mentions and replacement bytes were already checked above.
            verify_text_changes(
                canonical_original,
                canonical_output,
                normalized_edits(original, expected),
                local_ner,
                free_text=True,
                patient_name=patient_name,
                provider_name=provider_name,
            )


def _output_ranges(
    source: tuple[TextRange, ...], edits: tuple[TextEdit, ...]
) -> tuple[TextRange, ...]:
    """Carry source evidence forward; rewritten text cannot mint new exemptions."""
    return tuple(
        TextRange(
            start=span.start
            + sum(
                len(edit.replacement) - (edit.end - edit.start)
                for edit in edits
                if edit.end <= span.start
            ),
            end=span.end
            + sum(
                len(edit.replacement) - (edit.end - edit.start)
                for edit in edits
                if edit.end <= span.end
            ),
        )
        for span in source
    )
