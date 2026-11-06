"""Analyze every exposed native surface before accepting its identity evidence."""

import sqlite3
from collections import Counter

from redactor.formats.native import read_native
from redactor.identity.native import native_evidence
from redactor.persistence.files.artifacts import inspect_artifact
from redactor.persistence.files.results import write_step_result
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
from redactor.utils.errors import ERROR_INPUT_CHANGED
from redactor.utils.failures import failure_reason


def analyze_native_task(
    connection: sqlite3.Connection,
    task: Task,
    inspection: FileInspection,
    *,
    resources: ResourceSettings,
    mapping_key: bytes,
    detector: NerAdapter,
) -> StepResult:
    counts: Counter[str] = Counter()
    completed = 0
    reason = None
    try:
        before = inspect_artifact(task.input_path, persist=False)
        if before.sha256 != task.input_sha256 or before.size != task.input_size:
            raise ValueError(ERROR_INPUT_CHANGED)
        document = read_native(task.input_path, inspection, resources)
        facts: list[IdentityEvidence] = []
        for number, record in enumerate(document.records, start=1):
            evidence = native_evidence(record, task.input_sha256, number)
            facts.extend(
                fact
                for fact in (evidence.patient, evidence.provider)
                if fact is not None
            )
            for column in record.policies:
                found = cell_findings(
                    record.values[column.index],
                    column,
                    detector,
                    patient_name=evidence.patient.name if evidence.patient else "",
                    provider_name=evidence.provider.name if evidence.provider else "",
                )
                counts.update(finding.kind for finding in found)
            completed = number
        if inspect_artifact(task.input_path, persist=False) != before:
            raise ValueError(ERROR_INPUT_CHANGED)
        previous = scan_progress(connection, task.task_id)
        save_observation_batch(
            connection,
            task,
            facts,
            mapping_key,
            sequence=previous.sequence if previous else 1,
            input_offset=task.input_size,
            record_count=completed,
            counts=dict(counts),
        )
    except Exception as error:
        reason = failure_reason(error)
    return StepResult(
        artifact=write_step_result(
            connection,
            task,
            FileAnalysis(
                file_type=inspection.file_type,
                reason=reason,
                record_count=completed,
                counts=dict(counts),
            ),
            encryption_key=mapping_key,
        )
    )
