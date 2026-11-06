"""Map text findings to complete OCR words and protect nearby clinical pixels."""

import math
from collections import Counter

from redactor.inference.text import find_text_phi
from redactor.schemas.entities import NerAdapter
from redactor.schemas.ocr import OcrRegion
from redactor.schemas.pixels import PixelMask
from redactor.schemas.redaction import TextFinding, TextRange
from redactor.utils.constants import (
    PIXEL_MASK_HEIGHT_MARGIN,
    PIXEL_MASK_PADDING,
    PIXEL_TEXT,
)
from redactor.utils.errors import (
    ERROR_CLINICAL_CHANGED,
    ERROR_COVERAGE,
    ERROR_ENTITY_EVIDENCE,
)
from redactor.verification.residuals import protected_clinical_ranges, scan_residuals


def located_words(
    regions: tuple[OcrRegion, ...],
) -> tuple[str, tuple[tuple[TextRange, tuple[float, float, float, float]], ...]]:
    text = "\n".join(region.text for region in regions)
    located: list[tuple[TextRange, tuple[float, float, float, float]]] = []
    offset = 0
    for region in regions:
        cursor = 0
        for word in region.words or (region,):
            while cursor < len(region.text) and region.text[cursor].isspace():
                cursor += 1
            if not region.text.startswith(word.text, cursor):
                raise ValueError(ERROR_COVERAGE)
            end = cursor + len(word.text)
            located.append(
                (TextRange(start=offset + cursor, end=offset + end), word.box)
            )
            cursor = end
        if region.text[cursor:].strip():
            raise ValueError(ERROR_COVERAGE)
        offset += len(region.text) + 1
    return text, tuple(located)


def region_text_findings(
    regions: tuple[OcrRegion, ...],
    detector: NerAdapter,
    *,
    patient_name: str = "",
    provider_name: str = "",
) -> tuple[TextFinding, ...]:
    """Assess each OCR line, borrowing neighbour context for ambiguous lines.

    An isolated OCR line can lack the field labels the model needs to classify
    an observation. One retry joins the immediately adjacent lines so their
    context can ground the same observation on the target line. A line whose
    observation stays ambiguous or ungrounded fails closed exactly as before.
    """
    findings: list[TextFinding] = []
    offset = 0
    for index, region in enumerate(regions):
        try:
            located = find_text_phi(
                region.text,
                detector,
                patient_name=patient_name,
                provider_name=provider_name,
            )
        except ValueError as error:
            if error.args != (ERROR_COVERAGE,):
                raise
            located = neighbour_context_findings(
                regions,
                index,
                detector,
                patient_name=patient_name,
                provider_name=provider_name,
            )
        findings.extend(
            finding.model_copy(
                update={"start": finding.start + offset, "end": finding.end + offset}
            )
            for finding in located
        )
        offset += len(region.text) + 1
    return tuple(findings)


def neighbour_context_findings(
    regions: tuple[OcrRegion, ...],
    index: int,
    detector: NerAdapter,
    *,
    patient_name: str = "",
    provider_name: str = "",
) -> tuple[TextFinding, ...]:
    """Retry one ambiguous line with its neighbours, keeping only its findings."""
    prefix = [regions[index - 1].text] if index > 0 else []
    suffix = [regions[index + 1].text] if index + 1 < len(regions) else []
    target = regions[index].text
    target_offset = sum(len(part) + 1 for part in prefix)
    target_end = target_offset + len(target)
    try:
        located = find_text_phi(
            "\n".join([*prefix, target, *suffix]),
            detector,
            patient_name=patient_name,
            provider_name=provider_name,
        )
    except ValueError as error:
        if error.args != (ERROR_COVERAGE,):
            raise
        raise ValueError(ERROR_COVERAGE) from None
    grounded: list[TextFinding] = []
    for finding in located:
        if finding.end <= target_offset or target_end <= finding.start:
            # Entirely inside a neighbour: that line assesses it itself.
            continue
        if not (target_offset <= finding.start and finding.end <= target_end):
            # An observation crossing the line boundary cannot be projected
            # onto this line without masking words it never assessed.
            raise ValueError(ERROR_COVERAGE)
        start = finding.start - target_offset
        end = finding.end - target_offset
        if target[start:end] != finding.original:
            raise ValueError(ERROR_ENTITY_EVIDENCE)
        grounded.append(finding.model_copy(update={"start": start, "end": end}))
    if not grounded:
        # Neighbour context resolved nothing on this line; it stays unknown.
        raise ValueError(ERROR_COVERAGE)
    return tuple(grounded)


def text_pixel_masks(
    regions: tuple[OcrRegion, ...],
    size: tuple[int, int],
    detector: NerAdapter,
    *,
    patient_name: str = "",
    provider_name: str = "",
) -> tuple[tuple[PixelMask, ...], dict[str, int]]:
    text, words = located_words(regions)
    findings = region_text_findings(
        regions,
        detector,
        patient_name=patient_name,
        provider_name=provider_name,
    )
    protected = protected_clinical_ranges(text)
    selected = tuple(
        (span, box)
        for span, box in words
        if any(
            span.start < finding.end and finding.start < span.end
            for finding in findings
        )
    )
    for finding in findings:
        covered = {
            index for span, _ in selected for index in range(span.start, span.end)
        }
        if any(
            not text[index].isspace() and index not in covered
            for index in range(finding.start, finding.end)
        ):
            raise ValueError(ERROR_COVERAGE)
    masks = tuple(word_mask(box, size) for _, box in selected)
    for span, box in words:
        if any(
            span.start < clinical.end and clinical.start < span.end
            for clinical in protected
        ):
            if any(intersects(box, mask.box) for mask in masks):
                raise ValueError(ERROR_CLINICAL_CHANGED)
    # The unmasked source is independently scanned; incomplete names still fail.
    scan_image_text(text, tuple(span for span, _ in selected), detector)
    return masks, dict(Counter(finding.kind for finding in findings))


def word_mask(
    box: tuple[float, float, float, float], size: tuple[int, int]
) -> PixelMask:
    # Recognition alignment can clip glyph edges. Scale the margin with the
    # text height; the clinical-intersection check still rejects unsafe masks.
    margin = max(
        PIXEL_MASK_PADDING, math.ceil((box[3] - box[1]) * PIXEL_MASK_HEIGHT_MARGIN)
    )
    return PixelMask(
        box=(
            max(0, math.floor(box[0]) - margin),
            max(0, math.floor(box[1]) - margin),
            min(size[0], math.ceil(box[2]) + margin),
            min(size[1], math.ceil(box[3]) + margin),
        ),
        kind=PIXEL_TEXT,
    )


def scan_image_text(
    text: str, exemptions: tuple[TextRange, ...], detector: NerAdapter
) -> None:
    """OCR lines are spatial units, not one sentence across separate labels."""
    offset = 0
    for line in text.splitlines(keepends=True):
        value = line.rstrip("\r\n")
        spans = tuple(
            TextRange(
                start=max(span.start - offset, 0),
                end=min(span.end - offset, len(value)),
            )
            for span in exemptions
            if span.start < offset + len(value) and offset < span.end
        )
        scan_residuals(value, spans, detector)
        offset += len(line)


def intersects(
    first: tuple[float, float, float, float],
    second: tuple[float, float, float, float],
) -> bool:
    return (
        first[0] < second[2]
        and second[0] < first[2]
        and first[1] < second[3]
        and second[1] < first[3]
    )
