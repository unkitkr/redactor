"""Reparse every exposed native record and independently check its saved changes."""

import sqlite3
from collections import Counter

from redactor.formats.inspection import inspect_file
from redactor.formats.native import read_native
from redactor.identity.rows import row_context
from redactor.identity.tabular import row_evidence
from redactor.persistence.files.artifacts import inspect_artifact
from redactor.persistence.files.registration import prepare_successor
from redactor.persistence.files.results import read_step_result
from redactor.persistence.identities.snapshots import load_identity_lookup
from redactor.policy.tabular import cell_edits, cell_findings
from redactor.schemas.analysis import FileAnalysis
from redactor.schemas.configuration import PipelineSettings
from redactor.schemas.entities import NerAdapter
from redactor.schemas.formats import FileInspection
from redactor.schemas.persistence import Artifact, Task
from redactor.schemas.verification import VerificationCheck
from redactor.utils.constants import (
    FIELD_TEXT,
    FORMAT_XLSX,
    REQUIRED_VERIFICATION_CHECKS,
    STEP_ANALYZE,
    VERIFICATION_PASS,
)
from redactor.utils.errors import (
    ERROR_ARTIFACT_CORRUPT,
    ERROR_COVERAGE,
    ERROR_STRUCTURE,
)
from redactor.verification.text import verify_text_changes
from redactor.verification.xlsx import check_xlsx_surfaces


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
    output = read_native(artifact.path, written_inspection, settings.resources)
    if inspection.file_type == FORMAT_XLSX:
        check_xlsx_surfaces(artifact.path, output)
    if len(original.records) != len(output.records):
        raise ValueError(ERROR_COVERAGE)
    snapshot, lookup = load_identity_lookup(connection, resolution_task_id, mapping_key)
    analysis_id = prepare_successor(connection, task, STEP_ANALYZE).task_id
    analysis = read_step_result(
        connection, analysis_id, FileAnalysis, encryption_key=mapping_key
    )
    counts: Counter[str] = Counter()
    cells = 0
    for number, (before, after) in enumerate(
        zip(original.records, output.records, strict=True), start=1
    ):
        if before.locations != after.locations or len(before.values) != len(
            after.values
        ):
            raise ValueError(ERROR_COVERAGE)
        evidence = row_evidence(
            before.values, before.policies, task.input_sha256, number
        )
        context = row_context(
            evidence,
            lookup,
            analysis_id,
            task.input_sha256,
            number,
            mapping_key,
            snapshot.maximum_date_shift_days,
        )
        for column in before.policies:
            value = before.values[column.index]
            findings = cell_findings(
                value,
                column,
                local_ner,
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
            )
            counts.update(edit.kind for edit in edits)
            cells += 1
    if counts != analysis.counts or len(original.records) != analysis.record_count:
        raise ValueError(ERROR_COVERAGE)
    if inspect_artifact(task.input_path, persist=False) != source or (
        inspect_artifact(artifact.path, persist=False) != artifact
    ):
        raise ValueError(ERROR_ARTIFACT_CORRUPT)
    return tuple(
        VerificationCheck(
            kind=kind, status=VERIFICATION_PASS, expected=cells, checked=cells
        )
        for kind in REQUIRED_VERIFICATION_CHECKS
    )
