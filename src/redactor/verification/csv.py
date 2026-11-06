"""Validate every serialized cell, including row coverage and clinical invariants."""

import sqlite3
from collections import Counter
from contextlib import closing
from itertools import zip_longest

from redactor.formats.tabular_fields import column_policies
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
    REQUIRED_VERIFICATION_CHECKS,
    STEP_ANALYZE,
    STEP_INSPECT,
    VERIFICATION_PASS,
)
from redactor.utils.errors import (
    ERROR_ARTIFACT_CORRUPT,
    ERROR_COVERAGE,
    ERROR_STRUCTURE,
)
from redactor.verification.headers import verify_column_headers
from redactor.verification.reader import read_csv_rows
from redactor.verification.text import verify_text_changes


def verify_csv(
    connection: sqlite3.Connection,
    task: Task,
    artifact: Artifact,
    *,
    settings: PipelineSettings,
    mapping_key: bytes,
    local_ner: NerAdapter,
    resolution_task_id: str,
) -> tuple[VerificationCheck, ...]:
    source = inspect_artifact(task.input_path, persist=False)
    staged = inspect_artifact(artifact.path, persist=False)
    if (
        source.sha256 != task.input_sha256
        or source.size != task.input_size
        or staged != artifact
    ):
        raise ValueError(ERROR_ARTIFACT_CORRUPT)
    analysis_id = prepare_successor(connection, task, STEP_ANALYZE).task_id
    analysis = read_step_result(
        connection, analysis_id, FileAnalysis, encryption_key=mapping_key
    )
    inspection = read_step_result(
        connection,
        prepare_successor(connection, task, STEP_INSPECT).task_id,
        FileInspection,
        encryption_key=mapping_key,
    )
    layout = inspection.csv_layout
    if layout is None or analysis.reason is not None:
        raise ValueError(ERROR_STRUCTURE)
    snapshot, lookup = load_identity_lookup(connection, resolution_task_id, mapping_key)
    policies = column_policies(layout.columns)
    maximum = settings.resources.max_record_bytes
    counts: Counter[str] = Counter()
    cells = records = 0
    with (
        closing(read_csv_rows(task.input_path, layout.delimiter, maximum)) as original,
        closing(read_csv_rows(artifact.path, layout.delimiter, maximum)) as rewritten,
    ):
        if (
            next(original, None) != layout.columns
            or next(rewritten, None) != layout.columns
        ):
            raise ValueError(ERROR_STRUCTURE)
        verify_column_headers(layout.columns, local_ner)
        for number, pair in enumerate(zip_longest(original, rewritten), start=1):
            before, after = pair
            if (
                before is None
                or after is None
                or not (len(before) == len(after) == len(policies))
            ):
                raise ValueError(ERROR_COVERAGE)
            evidence = row_evidence(before, policies, task.input_sha256, number)
            context = row_context(
                evidence,
                lookup,
                analysis_id,
                task.input_sha256,
                number,
                mapping_key,
                snapshot.maximum_date_shift_days,
            )
            for column in policies:
                value = before[column.index]
                findings = cell_findings(
                    value,
                    column,
                    local_ner,
                    patient_name=context.patient_name,
                    provider_name=context.provider_name,
                )
                expected = cell_edits(value, column, findings, context, mapping_key)
                verify_text_changes(
                    value,
                    after[column.index],
                    expected,
                    local_ner,
                    free_text=column.kind == FIELD_TEXT,
                    patient_name=context.patient_name,
                    provider_name=context.provider_name,
                )
                counts.update(edit.kind for edit in expected)
                cells += 1
            records = number
    if records != analysis.record_count or counts != analysis.counts:
        raise ValueError(ERROR_COVERAGE)
    # Hash again after parsing to bind the verdict to bytes checked throughout.
    if inspect_artifact(artifact.path, persist=False) != artifact or (
        inspect_artifact(task.input_path, persist=False) != source
    ):
        raise ValueError(ERROR_ARTIFACT_CORRUPT)
    return tuple(
        VerificationCheck(
            kind=kind,
            status=VERIFICATION_PASS,
            expected=cells + len(layout.columns),
            checked=cells + len(layout.columns),
        )
        for kind in REQUIRED_VERIFICATION_CHECKS
    )
