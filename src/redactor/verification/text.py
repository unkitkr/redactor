"""Check exact edit locations and rescan serialized text without hiding context."""

import re
from unicodedata import normalize

from redactor.schemas.entities import NerAdapter
from redactor.schemas.redaction import TextEdit, TextRange
from redactor.schemas.verification import ResidualCheckCollector
from redactor.utils.constants import (
    FIELD_DATE,
    FIELD_EMAIL,
    FIELD_PATIENT_NAME,
    FIELD_PERSON_NAME,
    FIELD_PHONE,
    FIELD_PROVIDER_NAME,
    IMAGE_DESCRIPTION_FIELD_LABEL,
    UNICODE_NORMAL_FORM,
    VERIFIER_CONTACT_DATE_JOIN_PATTERN,
    VERIFIER_DATE_CUE_PATTERN,
    VERIFIER_DOCUMENT_HEADING_PREFIX_PATTERN,
    VERIFIER_EMAIL_CUE_PATTERN,
    VERIFIER_IMAGE_DESCRIPTOR_PATTERN,
    VERIFIER_NUMERIC_CANONICAL_KINDS,
    VERIFIER_PHONE_CUE_PATTERN,
    VERIFIER_SURFACE_PUNCTUATION,
)
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
    output_ner: NerAdapter | None = None,
    field_label: str = "",
    collect: ResidualCheckCollector | None = None,
) -> None:
    """An exemption belongs to one span, never every occurrence of its value."""
    source_end = output_end = 0
    source_ranges: list[TextRange] = []
    output_ranges: list[TextRange] = []
    clinical = protected_clinical_ranges(original) if free_text else ()
    structural = (
        _source_field_cues(original, expected)
        + _source_contact_date_joins(original, expected)
        + _source_document_heading(original, expected)
        + _source_image_descriptor(original, expected, field_label)
        if free_text
        else ()
    )
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
            structural=structural,
            collect=collect,
            numeric_spans=tuple(
                TextRange(start=edit.start, end=edit.end)
                for edit in expected
                if collect is not None and edit.kind in VERIFIER_NUMERIC_CANONICAL_KINDS
            ),
        )
        age_ranges = assessed_age_ranges(original)
        scan_residuals(
            output,
            tuple(output_ranges),
            output_ner or local_ner,
            patient_name=patient_name,
            provider_name=provider_name,
            clinical=_output_ranges(clinical, expected),
            assessed_ages=_output_ranges(age_ranges, expected),
            structural=_output_ranges(structural, expected),
            collect=collect if output_ner is None else None,
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
                output_ner=output_ner,
                field_label=field_label,
                collect=collect,
            )


def _source_contact_date_joins(
    text: str, edits: tuple[TextEdit, ...]
) -> tuple[TextRange, ...]:
    """A temporal preposition can relate two consecutive, verified typed edits."""
    return tuple(
        TextRange(start=contact.end, end=date.start)
        for contact, date in zip(edits, edits[1:], strict=False)
        if contact.kind in (FIELD_PHONE, FIELD_EMAIL)
        and date.kind == FIELD_DATE
        and re.fullmatch(
            VERIFIER_CONTACT_DATE_JOIN_PATTERN, text[contact.end : date.start]
        )
    )


def _source_document_heading(
    text: str, edits: tuple[TextEdit, ...]
) -> tuple[TextRange, ...]:
    """A document-type prefix ends at its delimiter and a confirmed edit."""
    for edit in edits:
        heading = re.fullmatch(
            VERIFIER_DOCUMENT_HEADING_PREFIX_PATTERN, text[: edit.start]
        )
        if heading:
            return (TextRange(start=heading.start(), end=heading.end()),)
    return ()


def _source_image_descriptor(
    text: str, edits: tuple[TextEdit, ...], field_label: str
) -> tuple[TextRange, ...]:
    """A typed image description can identify its descriptor, never extra names."""
    if field_label != IMAGE_DESCRIPTION_FIELD_LABEL or len(edits) != 1:
        return ()
    edit = edits[0]
    if edit.kind not in (FIELD_PERSON_NAME, FIELD_PATIENT_NAME, FIELD_PROVIDER_NAME):
        return ()
    prefix = re.fullmatch(VERIFIER_IMAGE_DESCRIPTOR_PATTERN, text[: edit.start])
    if prefix and re.fullmatch(VERIFIER_SURFACE_PUNCTUATION, text[edit.end :]):
        return (TextRange(start=prefix.start(), end=prefix.end()),)
    return ()


def _source_field_cues(text: str, edits: tuple[TextEdit, ...]) -> tuple[TextRange, ...]:
    """Only a typed edit can establish its immediately preceding field label."""
    ranges: list[TextRange] = []
    for edit in edits:
        pattern = (
            VERIFIER_PHONE_CUE_PATTERN
            if edit.kind == FIELD_PHONE
            else VERIFIER_EMAIL_CUE_PATTERN
            if edit.kind == FIELD_EMAIL
            else VERIFIER_DATE_CUE_PATTERN
            if edit.kind == FIELD_DATE
            else None
        )
        if pattern is not None:
            match = re.search(pattern, text[: edit.start])
            if match is not None:
                ranges.append(TextRange(start=match.start(), end=match.end()))
    return tuple(ranges)


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
