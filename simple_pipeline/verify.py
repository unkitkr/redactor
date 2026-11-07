"""Reopen saved bytes and check native structures, text and pixels independently."""

from pathlib import Path

from redactor.formats.inspection import inspect_file
from redactor.formats.native import read_native
from redactor.inference.context import record_ner
from redactor.policy.tabular import cell_edits, cell_findings
from redactor.schemas.configuration import PipelineSettings
from redactor.schemas.entities import NerAdapter
from redactor.schemas.native import NativeDocument, NativeRecord
from redactor.schemas.simple import ExtractedFile, RedactedFile
from redactor.utils.constants import (
    FIELD_TEXT,
    FORMAT_DICOM,
    FORMAT_DOCX,
    FORMAT_FHIR,
    FORMAT_HL7,
    FORMAT_JSON,
    FORMAT_PDF,
    FORMAT_XLSX,
    IMAGE_FORMATS,
    TEXT_ENCODING,
)
from redactor.utils.errors import (
    ERROR_ARTIFACT_CORRUPT,
    ERROR_COVERAGE,
    ERROR_REPLACEMENT,
    ERROR_STRUCTURE,
)
from redactor.verification.archive import check_saved_archive
from redactor.verification.dicom import check_dicom_structure
from redactor.verification.docx import check_docx_structure
from redactor.verification.embedded_images import verify_embedded_images
from redactor.verification.fhir import check_fhir_structure
from redactor.verification.headers import verify_column_headers
from redactor.verification.hl7 import check_hl7_surfaces
from redactor.verification.images import verify_image_content
from redactor.verification.json import check_json_surfaces
from redactor.verification.pdf import check_pdf_structure
from redactor.verification.reader import read_csv_rows
from redactor.verification.text import verify_text_changes
from redactor.verification.xlsx import check_xlsx_surfaces
from redactor.verification.xlsx_preservation import check_xlsx_preservation
from redactor.verification.xlsx_source import check_xlsx_source_surfaces
from redactor.verification.xlsx_tooling import check_workbook_tooling
from simple_pipeline.content import file_digest


def verify_saved(
    plan: RedactedFile,
    output: Path,
    settings: PipelineSettings,
    verifier: NerAdapter,
    key: bytes,
) -> str:
    source = plan.analysis.source
    digest = file_digest(output)
    if file_digest(source.path) != source.sha256:
        raise ValueError(ERROR_ARTIFACT_CORRUPT)
    inspection = inspect_file(output, settings.resources)
    if inspection.reason or inspection.file_type != source.inspection.file_type:
        raise ValueError(ERROR_STRUCTURE)
    if inspection.file_type in IMAGE_FORMATS:
        verify_image_content(
            source.path,
            output,
            plan.analysis.frames,
            inspection.file_type.upper(),
            settings,
            verifier,
        )
    else:
        saved = read_saved(source, output, settings, verifier)
        check_structure(source, output, saved, settings)
        verify_embedded_images(
            source.document, saved, plan.analysis.images, settings, verifier
        )
        verify_records(plan, saved, settings, verifier, key)
    if file_digest(output) != digest or file_digest(source.path) != source.sha256:
        raise ValueError(ERROR_ARTIFACT_CORRUPT)
    return digest


def read_saved(
    source: ExtractedFile,
    output: Path,
    settings: PipelineSettings,
    verifier: NerAdapter,
) -> NativeDocument:
    layout = source.inspection.csv_layout
    if layout is None:
        return read_native(
            output, source.inspection, settings.resources, extract_evidence=False
        )
    verify_column_headers(layout.columns, verifier)
    rows = read_csv_rows(output, layout.delimiter, settings.resources.max_record_bytes)
    try:
        if next(rows, None) != layout.columns:
            raise ValueError(ERROR_STRUCTURE)
        records: list[NativeRecord] = []
        for number, values in enumerate(rows):
            if number >= len(source.document.records):
                raise ValueError(ERROR_COVERAGE)
            before = source.document.records[number]
            if len(values) != len(before.values):
                raise ValueError(ERROR_COVERAGE)
            records.append(before.model_copy(update={"values": values}))
    finally:
        rows.close()
    return NativeDocument(records=tuple(records))


def check_structure(
    source: ExtractedFile,
    output: Path,
    saved: NativeDocument,
    settings: PipelineSettings,
) -> None:
    original, document = source.path, source.document
    file_type = source.inspection.file_type
    if file_type == FORMAT_PDF:
        check_pdf_structure(original, output, document)
    elif file_type == FORMAT_FHIR:
        check_fhir_structure(original, output, document, settings.resources)
    elif file_type == FORMAT_DICOM:
        check_dicom_structure(original, output, document)
    elif file_type == FORMAT_DOCX:
        check_docx_structure(original, output)
    elif file_type == FORMAT_XLSX:
        check_saved_archive(output)
        check_xlsx_source_surfaces(original, document)
        check_xlsx_surfaces(output, saved)
        check_xlsx_preservation(original, output, document)
        check_workbook_tooling(output)
    elif file_type == FORMAT_HL7:
        check_hl7_surfaces(
            original, output, document, source.inspection.encoding or TEXT_ENCODING
        )
    elif file_type == FORMAT_JSON:
        check_json_surfaces(original, output, document, settings.resources)


def verify_records(
    plan: RedactedFile,
    saved: NativeDocument,
    settings: PipelineSettings,
    verifier: NerAdapter,
    key: bytes,
) -> None:
    original = plan.analysis.source.document
    if len(original.records) != len(saved.records):
        raise ValueError(ERROR_COVERAGE)
    seen: set[tuple[str, ...]] = set()
    for before, after, context, edits in zip(
        original.records, saved.records, plan.contexts, plan.edits, strict=True
    ):
        if (
            before.locations != after.locations
            or before.policies != after.policies
            or before.field_labels != after.field_labels
            or len(before.values) != len(after.values)
        ):
            raise ValueError(ERROR_COVERAGE)
        for column in before.policies:
            index = column.index
            location = after.locations[index]
            if not location or location in seen:
                raise ValueError(ERROR_COVERAGE)
            seen.add(location)
            # Typed-field coverage and replacements are recomputed from the
            # original values; an empty writer edit list cannot exempt a name.
            if column.kind != FIELD_TEXT:
                value = before.values[index]
                expected = cell_edits(
                    value, column, cell_findings(value, column, verifier), context, key
                )
                if expected != edits[index]:
                    raise ValueError(ERROR_REPLACEMENT)
            verify_text_changes(
                before.values[index],
                after.values[index],
                edits[index],
                record_ner(verifier, before, index, settings.local.ner_max_characters),
                output_ner=record_ner(
                    verifier, after, index, settings.local.ner_max_characters
                ),
                field_label=before.field_labels[index] if before.field_labels else "",
                free_text=column.kind == FIELD_TEXT,
                patient_name=context.patient_name,
                provider_name=context.provider_name,
            )
