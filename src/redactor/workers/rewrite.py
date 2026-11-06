"""Stream native CSV output with durable complete-record checkpoints."""

import hashlib
import sqlite3
from collections import Counter

from redactor.formats.csv import encode_csv_header, encode_csv_record, iter_csv_records
from redactor.formats.tabular_fields import column_policies
from redactor.identity.rows import row_context
from redactor.identity.tabular import row_evidence
from redactor.persistence.files.artifacts import (
    create_temporary_file,
    seal_temporary_file,
)
from redactor.persistence.files.checkpoints import resume_checkpoint, save_checkpoint
from redactor.persistence.files.registration import prepare_successor
from redactor.persistence.files.results import read_step_result
from redactor.persistence.identities.snapshots import load_identity_lookup
from redactor.policy.tabular import cell_edits, cell_findings
from redactor.policy.text import apply_text_edits
from redactor.schemas.analysis import FileAnalysis
from redactor.schemas.configuration import PipelineSettings
from redactor.schemas.entities import NerAdapter
from redactor.schemas.formats import FileInspection
from redactor.schemas.persistence import Checkpoint, Task
from redactor.schemas.pipeline import StepResult
from redactor.utils.constants import (
    CSV_ADAPTER_VERSION,
    HASH_CHUNK_BYTES,
    STEP_ANALYZE,
    STEP_INSPECT,
    STEP_VERIFY,
)
from redactor.utils.errors import (
    ERROR_COVERAGE,
    ERROR_FORMAT_UNSUPPORTED,
    ERROR_RESOURCE_LIMIT,
)


def rewrite_task(
    connection: sqlite3.Connection,
    task: Task,
    *,
    settings: PipelineSettings,
    mapping_key: bytes,
    local_ner: NerAdapter,
    resolution_task_id: str,
) -> StepResult:
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
    if analysis.reason is not None or inspection.csv_layout is None:
        raise ValueError(ERROR_FORMAT_UNSUPPORTED)
    snapshot, lookup = load_identity_lookup(connection, resolution_task_id, mapping_key)
    layout = inspection.csv_layout
    policies = column_policies(layout.columns)
    resources = settings.resources
    checkpoint = resume_checkpoint(connection, task, CSV_ADAPTER_VERSION)
    path = (
        checkpoint.artifact_path
        if checkpoint
        else create_temporary_file(connection, task)
    )
    counts: Counter[str] = Counter(checkpoint.counts if checkpoint else {})
    offset = checkpoint.input_offset if checkpoint else layout.header_end_offset
    completed = checkpoint.record_count if checkpoint else 0
    digest = hashlib.sha256()
    with path.open("r+b") as stream:
        if checkpoint:
            remaining = checkpoint.output_offset
            while remaining:
                payload = stream.read(min(remaining, HASH_CHUNK_BYTES))
                if not payload:
                    raise ValueError(ERROR_COVERAGE)
                digest.update(payload)
                remaining -= len(payload)
        else:
            stream.truncate(0)
            header = encode_csv_header(layout)
            stream.write(header)
            digest.update(header)
        for row in iter_csv_records(
            task.input_path,
            layout,
            resources.max_record_bytes,
            start_offset=offset,
            completed_records=completed,
        ):
            evidence = row_evidence(row.values, policies, task.input_sha256, row.number)
            context = row_context(
                evidence,
                lookup,
                analysis_id,
                task.input_sha256,
                row.number,
                mapping_key,
                snapshot.maximum_date_shift_days,
            )
            rewritten: list[str] = []
            for column in policies:
                value = row.values[column.index]
                findings = cell_findings(
                    value,
                    column,
                    local_ner,
                    patient_name=context.patient_name,
                    provider_name=context.provider_name,
                )
                edits = cell_edits(value, column, findings, context, mapping_key)
                rewritten.append(apply_text_edits(value, edits))
                counts.update(edit.kind for edit in edits)
            payload = encode_csv_record(rewritten, layout)
            if len(payload) > resources.max_record_bytes:
                raise ValueError(ERROR_RESOURCE_LIMIT)
            stream.write(payload)
            digest.update(payload)
            completed, offset = row.number, row.end_offset
            if completed % resources.checkpoint_records == 0:
                stream.flush()
                checkpoint = Checkpoint(
                    sequence=checkpoint.sequence + 1 if checkpoint else 1,
                    task_id=task.task_id,
                    artifact_path=path,
                    input_offset=offset,
                    output_offset=stream.tell(),
                    record_count=completed,
                    output_prefix_sha256=digest.hexdigest(),
                    counts=dict(counts),
                    adapter_version=CSV_ADAPTER_VERSION,
                )
                save_checkpoint(connection, task, checkpoint)
        if checkpoint is None or offset != checkpoint.input_offset:
            stream.flush()
            save_checkpoint(
                connection,
                task,
                Checkpoint(
                    sequence=checkpoint.sequence + 1 if checkpoint else 1,
                    task_id=task.task_id,
                    artifact_path=path,
                    input_offset=offset,
                    output_offset=stream.tell(),
                    record_count=completed,
                    output_prefix_sha256=digest.hexdigest(),
                    counts=dict(counts),
                    adapter_version=CSV_ADAPTER_VERSION,
                ),
            )
    if (
        completed != analysis.record_count
        or counts != analysis.counts
        or offset != task.input_size
    ):
        raise ValueError(ERROR_COVERAGE)
    return StepResult(
        artifact=seal_temporary_file(connection, task),
        successors=(prepare_successor(connection, task, STEP_VERIFY),),
    )
