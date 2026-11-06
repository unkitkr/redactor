"""Reparse every exposed native record and independently check its saved changes."""

import sqlite3
from collections import Counter

from redactor.agents.detector.adapter import detection_adapter
from redactor.formats.inspection import inspect_file
from redactor.formats.native import read_native
from redactor.identity.native import native_evidence
from redactor.identity.rows import row_context
from redactor.persistence.files.artifacts import inspect_artifact
from redactor.persistence.files.registration import prepare_successor
from redactor.persistence.files.results import read_step_result
from redactor.persistence.identities.snapshots import load_identity_lookup
from redactor.policy.tabular import cell_edits, cell_findings
from redactor.schemas.analysis import FileAnalysis
from redactor.schemas.configuration import PipelineSettings
from redactor.schemas.entities import NerAdapter
from redactor.schemas.formats import FileInspection
from redactor.schemas.native import NativeDocument
from redactor.schemas.persistence import Artifact, Task
from redactor.schemas.verification import VerificationCheck
from redactor.utils.constants import (
    CHECK_PIXELS,
    FIELD_TEXT,
    FORMAT_DICOM,
    FORMAT_DOCX,
    FORMAT_FHIR,
    FORMAT_HL7,
    FORMAT_JSON,
    FORMAT_PDF,
    FORMAT_XLSX,
    REQUIRED_VERIFICATION_CHECKS,
    STEP_ANALYZE,
    TEXT_ENCODING,
    VERIFICATION_PASS,
)
from redactor.utils.errors import (
    ERROR_ARTIFACT_CORRUPT,
    ERROR_COVERAGE,
    ERROR_STRUCTURE,
)
from redactor.verification.archive import check_saved_archive
from redactor.verification.dicom import check_dicom_structure
from redactor.verification.docx import check_docx_structure
from redactor.verification.embedded_images import verify_embedded_images
from redactor.verification.fhir import check_fhir_structure
from redactor.verification.hl7 import check_hl7_surfaces
from redactor.verification.json import check_json_surfaces
from redactor.verification.pdf import check_pdf_structure
from redactor.verification.text import verify_text_changes
from redactor.verification.xlsx import check_xlsx_surfaces
from redactor.verification.xlsx_preservation import check_xlsx_preservation
from redactor.verification.xlsx_source import check_xlsx_source_surfaces
from redactor.verification.xlsx_tooling import check_workbook_tooling


def verify_native(
    connection: sqlite3.Connection,
    task: Task,
    artifact: Artifact,
    inspection: FileInspection,
    *,
    settings: PipelineSettings,
    mapping_key: bytes,
    local_ner: NerAdapter,
    resolution_task_id: str,
) -> tuple[VerificationCheck, ...]:
    source = inspect_artifact(task.input_path, persist=False)
    if (
        source.sha256 != task.input_sha256
        or source.size != task.input_size
        or (inspect_artifact(artifact.path, persist=False) != artifact)
    ):
        raise ValueError(ERROR_ARTIFACT_CORRUPT)
    written_inspection = inspect_file(artifact.path, settings.resources)
    if (
        written_inspection.reason is not None
        or written_inspection.file_type != inspection.file_type
    ):
        raise ValueError(ERROR_STRUCTURE)
    original = read_native(task.input_path, inspection, settings.resources)
    output = read_native(
        artifact.path, written_inspection, settings.resources, extract_evidence=False
    )
    _validate_locations(original)
    _validate_locations(output)
    if inspection.file_type == FORMAT_PDF:
        check_pdf_structure(task.input_path, artifact.path, original)
    if inspection.file_type == FORMAT_FHIR:
        check_fhir_structure(
            task.input_path, artifact.path, original, settings.resources
        )
    if inspection.file_type == FORMAT_DICOM:
        check_dicom_structure(task.input_path, artifact.path, original)
    if inspection.file_type == FORMAT_DOCX:
        check_docx_structure(task.input_path, artifact.path)
    if inspection.file_type == FORMAT_XLSX:
        check_saved_archive(artifact.path)
        check_xlsx_source_surfaces(task.input_path, original)
        check_xlsx_surfaces(artifact.path, output)
        check_xlsx_preservation(task.input_path, artifact.path, original)
        check_workbook_tooling(artifact.path)
    if inspection.file_type == FORMAT_HL7:
        check_hl7_surfaces(
            task.input_path,
            artifact.path,
            original,
            inspection.encoding or TEXT_ENCODING,
        )
    if inspection.file_type == FORMAT_JSON:
        check_json_surfaces(
            task.input_path, artifact.path, original, settings.resources
        )
    if len(original.records) != len(output.records):
        raise ValueError(ERROR_COVERAGE)
    snapshot, lookup = load_identity_lookup(connection, resolution_task_id, mapping_key)
    analysis_id = prepare_successor(connection, task, STEP_ANALYZE).task_id
    analysis = read_step_result(
        connection, analysis_id, FileAnalysis, encryption_key=mapping_key
    )
    if analysis.reason is not None or analysis.file_type != inspection.file_type:
        raise ValueError(ERROR_COVERAGE)
    detector = detection_adapter(
        connection,
        task,
        settings=settings,
        mapping_key=mapping_key,
        local_ner=local_ner,
    )
    counts: Counter[str] = Counter()
    image_frames = verify_embedded_images(
        original, output, analysis.embedded_images, settings, local_ner
    )
    for image in analysis.embedded_images:
        counts.update(image.counts)
    cells = 0
    for number, (before, after) in enumerate(
        zip(original.records, output.records, strict=True), start=1
    ):
        if (
            before.locations != after.locations
            or before.policies != after.policies
            or len(before.values) != len(after.values)
        ):
            raise ValueError(ERROR_COVERAGE)
        evidence = native_evidence(before, task.input_sha256, number)
        context = row_context(
            evidence,
            lookup,
            analysis_id,
            task.input_sha256,
            number,
            mapping_key,
            snapshot.maximum_date_shift_days,
            context_scope=before.context_scope,
        )
        for column in before.policies:
            value = before.values[column.index]
            findings = cell_findings(
                value,
                column,
                detector,
                patient_name=context.patient_name,
                provider_name=context.provider_name,
            )
            edits = cell_edits(value, column, findings, context, mapping_key)
            verify_text_changes(
                value,
                after.values[column.index],
                edits,
                local_ner,
                free_text=column.kind == FIELD_TEXT,
                patient_name=context.patient_name,
                provider_name=context.provider_name,
            )
            counts.update(edit.kind for edit in edits)
            cells += 1
    if counts != analysis.counts or len(original.records) != analysis.record_count:
        raise ValueError(ERROR_COVERAGE)
    if inspect_artifact(task.input_path, persist=False) != source or (
        inspect_artifact(artifact.path, persist=False) != artifact
    ):
        raise ValueError(ERROR_ARTIFACT_CORRUPT)
    checks = tuple(
        VerificationCheck(
            kind=kind, status=VERIFICATION_PASS, expected=cells, checked=cells
        )
        for kind in REQUIRED_VERIFICATION_CHECKS
    )
    if image_frames:
        checks += (
            VerificationCheck(
                kind=CHECK_PIXELS,
                status=VERIFICATION_PASS,
                expected=image_frames,
                checked=image_frames,
            ),
        )
    return checks


def _validate_locations(document: NativeDocument) -> None:
    seen: set[tuple[str, ...]] = set()
    for record in document.records:
        if not len(record.values) == len(record.locations) == len(record.policies):
            raise ValueError(ERROR_COVERAGE)
        if tuple(policy.index for policy in record.policies) != tuple(
            range(len(record.values))
        ):
            raise ValueError(ERROR_COVERAGE)
        for location in record.locations:
            if not location or location in seen:
                raise ValueError(ERROR_COVERAGE)
            seen.add(location)
