"""Detect once, then turn the findings into deterministic native edits."""

from redactor.formats.embedded_images import (
    analyze_embedded_image,
    embedded_pixel_count,
)
from redactor.identity.native import native_evidence
from redactor.identity.rows import row_context
from redactor.inference.context import record_ner
from redactor.inference.images import analyze_image_content
from redactor.policy.tabular import cell_edits, cell_findings
from redactor.schemas.configuration import PipelineSettings
from redactor.schemas.entities import NerAdapter
from redactor.schemas.identity import IdentityLookup
from redactor.schemas.ocr import OcrAdapter
from redactor.schemas.pixels import EmbeddedImageEvidence
from redactor.schemas.redaction import TextContext, TextEdit, TextFinding
from redactor.schemas.simple import AnalyzedFile, ExtractedFile, RedactedFile
from redactor.utils.constants import IMAGE_FORMATS
from redactor.verification.headers import verify_column_headers


def analyze_file(
    source: ExtractedFile,
    settings: PipelineSettings,
    detector: NerAdapter,
    ocr: OcrAdapter,
) -> AnalyzedFile:
    if source.inspection.file_type in IMAGE_FORMATS:
        frames, _ = analyze_image_content(source.path, settings, detector, ocr)
        return AnalyzedFile(source=source, findings=(), frames=frames)
    if source.inspection.csv_layout is not None:
        verify_column_headers(source.inspection.csv_layout.columns, detector)
    patient_names = {
        record.evidence.patient.name
        for record in source.document.records
        if record.evidence and record.evidence.patient and record.evidence.patient.name
    }
    provider_names = {
        record.evidence.provider.name
        for record in source.document.records
        if record.evidence
        and record.evidence.provider
        and record.evidence.provider.name
    }
    images: list[EmbeddedImageEvidence] = []
    pixels = 0
    for image in source.document.images:
        pixels += embedded_pixel_count(
            image, settings.resources.max_image_pixels - pixels
        )
        images.append(
            analyze_embedded_image(
                image,
                settings,
                detector,
                ocr,
                patient_name=next(iter(patient_names))
                if len(patient_names) == 1
                else "",
                provider_name=next(iter(provider_names))
                if len(provider_names) == 1
                else "",
            )
        )
    findings: list[tuple[tuple[TextFinding, ...], ...]] = []
    for number, record in enumerate(source.document.records, 1):
        evidence = native_evidence(record, source.sha256, number)
        findings.append(
            tuple(
                cell_findings(
                    record.values[column.index],
                    column,
                    record_ner(
                        detector,
                        record,
                        column.index,
                        settings.local.ner_max_characters,
                    ),
                    patient_name=evidence.patient.name if evidence.patient else "",
                    provider_name=evidence.provider.name if evidence.provider else "",
                )
                for column in record.policies
            )
        )
    return AnalyzedFile(source=source, findings=tuple(findings), images=tuple(images))


def redact_file(
    analysis: AnalyzedFile,
    lookup: IdentityLookup,
    key: bytes,
    settings: PipelineSettings,
) -> RedactedFile:
    contexts: list[TextContext] = []
    edits: list[tuple[tuple[TextEdit, ...], ...]] = []
    source = analysis.source
    for number, (record, findings) in enumerate(
        zip(source.document.records, analysis.findings, strict=True), 1
    ):
        context = row_context(
            native_evidence(record, source.sha256, number),
            lookup,
            source.sha256,
            source.sha256,
            number,
            key,
            settings.policy.maximum_date_shift_days,
            context_scope=record.context_scope,
        )
        contexts.append(context)
        edits.append(
            tuple(
                cell_edits(
                    record.values[column.index],
                    column,
                    findings[column.index],
                    context,
                    key,
                )
                for column in record.policies
            )
        )
    return RedactedFile(analysis=analysis, contexts=tuple(contexts), edits=tuple(edits))
