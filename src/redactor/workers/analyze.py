"""Analyze every CSV record and checkpoint identity facts and finding counts."""

import sqlite3
from collections import Counter

from redactor.formats.csv import iter_csv_records
from redactor.formats.tabular_fields import column_policies
from redactor.identity.tabular import row_evidence
from redactor.inference.text import find_text_phi
from redactor.persistence.files.artifacts import inspect_artifact
from redactor.persistence.files.hashing import file_version
from redactor.persistence.files.registration import prepare_successor
from redactor.persistence.files.results import read_step_result, write_step_result
from redactor.persistence.identities.observations import (
    save_observation_batch,
    scan_progress,
)
from redactor.policy.tabular import cell_findings
from redactor.schemas.analysis import FileAnalysis
from redactor.schemas.configuration import ResourceSettings
from redactor.schemas.entities import NerAdapter
from redactor.schemas.formats import FileInspection
from redactor.schemas.identity import IdentityEvidence
from redactor.schemas.persistence import Task
from redactor.schemas.pipeline import StepResult
from redactor.utils.constants import (
    FIELD_TEXT,
    FORMAT_CSV,
    FORMAT_TSV,
    IDENTITY_BATCH_LIMIT,
    MAX_PRIVATE_RECORD_BYTES,
    STEP_INSPECT,
)
from redactor.utils.errors import (
    ERROR_FORMAT_UNSUPPORTED,
    ERROR_INPUT_CHANGED,
    ERROR_RESOURCE_LIMIT,
)
from redactor.utils.failures import failure_reason
from redactor.workers.analyze_native import analyze_native_task


def analyze_task(
    connection: sqlite3.Connection,
    task: Task,
    *,
    resources: ResourceSettings,
    mapping_key: bytes,
    local_ner: NerAdapter,
) -> StepResult:
    inspection_id = prepare_successor(connection, task, STEP_INSPECT).task_id
    inspection = read_step_result(
        connection, inspection_id, FileInspection, encryption_key=mapping_key
    )
    progress = scan_progress(connection, task.task_id)
    counts: Counter[str] = Counter(progress.counts if progress else {})
    completed = progress.record_count if progress else 0
    reason = inspection.reason
    try:
        if reason is None:
            if (
                inspection.file_type not in (FORMAT_CSV, FORMAT_TSV)
                or inspection.csv_layout is None
            ):
                return analyze_native_task(
                    connection,
                    task,
                    inspection,
                    resources=resources,
                    mapping_key=mapping_key,
                    local_ner=local_ner,
                )
            before = file_version(task.input_path.stat())
            original = inspect_artifact(task.input_path, persist=False)
            if original.sha256 != task.input_sha256 or original.size != task.input_size:
                raise ValueError(ERROR_INPUT_CHANGED)
            layout = inspection.csv_layout
            policies = column_policies(layout.columns)
            for column in policies:
                if column.kind == FIELD_TEXT and find_text_phi(
                    layout.columns[column.index], local_ner
                ):
                    raise ValueError(ERROR_FORMAT_UNSUPPORTED)
            batch: list[IdentityEvidence] = []
            batch_bytes = 0
            offset = progress.input_offset if progress else layout.header_end_offset
            for row in iter_csv_records(
                task.input_path,
                layout,
                resources.max_record_bytes,
                start_offset=offset,
                completed_records=completed,
            ):
                evidence = row_evidence(
                    row.values, policies, task.input_sha256, row.number
                )
                facts = tuple(
                    fact
                    for fact in (evidence.patient, evidence.provider)
                    if fact is not None
                )
                size = sum(len(fact.model_dump_json().encode()) for fact in facts)
                if size > MAX_PRIVATE_RECORD_BYTES:
                    raise ValueError(ERROR_RESOURCE_LIMIT)
                if batch and batch_bytes + size > MAX_PRIVATE_RECORD_BYTES:
                    progress = save_observation_batch(
                        connection,
                        task,
                        batch,
                        mapping_key,
                        sequence=progress.sequence + 1 if progress else 1,
                        input_offset=offset,
                        record_count=completed,
                        counts=dict(counts),
                    )
                    batch.clear()
                    batch_bytes = 0
                for column in policies:
                    found = cell_findings(
                        row.values[column.index],
                        column,
                        local_ner,
                        patient_name=evidence.patient.name if evidence.patient else "",
                        provider_name=evidence.provider.name
                        if evidence.provider
                        else "",
                    )
                    counts.update(finding.kind for finding in found)
                batch.extend(facts)
                batch_bytes += size
                offset, completed = row.end_offset, row.number
                if (
                    completed % resources.checkpoint_records == 0
                    or len(batch) >= IDENTITY_BATCH_LIMIT
                ):
                    progress = save_observation_batch(
                        connection,
                        task,
                        batch,
                        mapping_key,
                        sequence=progress.sequence + 1 if progress else 1,
                        input_offset=offset,
                        record_count=completed,
                        counts=dict(counts),
                    )
                    batch.clear()
                    batch_bytes = 0
            if progress is None or offset != progress.input_offset:
                save_observation_batch(
                    connection,
                    task,
                    batch,
                    mapping_key,
                    sequence=progress.sequence + 1 if progress else 1,
                    input_offset=offset,
                    record_count=completed,
                    counts=dict(counts),
                )
            if file_version(task.input_path.stat()) != before:
                raise ValueError(ERROR_INPUT_CHANGED)
    except Exception as error:
        reason = failure_reason(error)
    summary = FileAnalysis(
        file_type=inspection.file_type,
        record_count=completed,
        reason=reason,
        counts=dict(counts),
    )
    return StepResult(
        artifact=write_step_result(
            connection, task, summary, encryption_key=mapping_key
        )
    )
