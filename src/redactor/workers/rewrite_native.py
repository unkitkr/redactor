"""Rewrite bounded native documents and record the fully staged artifact."""

import sqlite3
from collections import Counter

from redactor.formats.native import read_native, write_native
from redactor.identity.rows import row_context
from redactor.identity.tabular import row_evidence
from redactor.persistence.files.artifacts import (
    create_temporary_file,
    seal_temporary_file,
)
from redactor.persistence.files.checkpoints import latest_checkpoint, save_checkpoint
from redactor.persistence.files.registration import prepare_successor
from redactor.persistence.identities.snapshots import load_identity_lookup
from redactor.policy.tabular import cell_edits, cell_findings
from redactor.policy.text import apply_text_edits
from redactor.schemas.analysis import FileAnalysis
from redactor.schemas.configuration import PipelineSettings
from redactor.schemas.entities import NerAdapter
from redactor.schemas.formats import FileInspection
from redactor.schemas.persistence import Checkpoint, Task
from redactor.schemas.pipeline import StepResult
from redactor.utils.constants import NATIVE_ADAPTER_VERSION, STEP_ANALYZE, STEP_VERIFY
from redactor.utils.errors import ERROR_COVERAGE


def rewrite_native_task(
    connection: sqlite3.Connection,
    task: Task,
    inspection: FileInspection,
    analysis: FileAnalysis,
    *,
    settings: PipelineSettings,
    mapping_key: bytes,
    local_ner: NerAdapter,
    resolution_task_id: str,
) -> StepResult:
    document = read_native(task.input_path, inspection, settings.resources)
    snapshot, lookup = load_identity_lookup(connection, resolution_task_id, mapping_key)
    analysis_id = prepare_successor(connection, task, STEP_ANALYZE).task_id
    replacements: dict[tuple[str, ...], str] = {}
    counts: Counter[str] = Counter()
    for number, record in enumerate(document.records, start=1):
        evidence = row_evidence(
            record.values, record.policies, task.input_sha256, number
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
        for column in record.policies:
            value = record.values[column.index]
            findings = cell_findings(
                value,
                column,
                local_ner,
                patient_name=context.patient_name,
                provider_name=context.provider_name,
            )
            edits = cell_edits(value, column, findings, context, mapping_key)
            if edits:
                replacements[record.locations[column.index]] = apply_text_edits(
                    value, edits
                )
            counts.update(edit.kind for edit in edits)
    if counts != analysis.counts or len(document.records) != analysis.record_count:
        raise ValueError(ERROR_COVERAGE)
    path = create_temporary_file(connection, task)
    write_native(task.input_path, path, inspection, replacements)
    artifact = seal_temporary_file(connection, task)
    previous = latest_checkpoint(connection, task.task_id)
    save_checkpoint(
        connection,
        task,
        Checkpoint(
            sequence=previous.sequence + 1 if previous else 1,
            task_id=task.task_id,
            artifact_path=path,
            input_offset=task.input_size,
            output_offset=artifact.size,
            record_count=len(document.records),
            output_prefix_sha256=artifact.sha256,
            counts=dict(counts),
            adapter_version=NATIVE_ADAPTER_VERSION,
        ),
    )
    return StepResult(
        artifact=artifact,
        successors=(prepare_successor(connection, task, STEP_VERIFY),),
    )
