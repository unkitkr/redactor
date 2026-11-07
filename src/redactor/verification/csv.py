"""Validate every serialized cell, including row coverage and clinical invariants."""

import sqlite3
from collections import Counter, OrderedDict
from collections.abc import Iterator
from contextlib import closing
from itertools import zip_longest

from redactor.agents.detector.adapter import detection_adapter
from redactor.formats.tabular_fields import column_policies
from redactor.identity.evidence import observation_preparer
from redactor.identity.rows import row_context
from redactor.identity.tabular import make_row_evidence
from redactor.inference.text import make_text_finder
from redactor.persistence.files.artifacts import inspect_artifact
from redactor.persistence.files.registration import prepare_successor
from redactor.persistence.files.results import read_step_result
from redactor.persistence.identities.snapshots import load_identity_lookup
from redactor.policy.tabular import cell_edits, cell_findings
from redactor.policy.tabular_runtime import typed_column_operations
from redactor.schemas.analysis import FileAnalysis
from redactor.schemas.configuration import PipelineSettings
from redactor.schemas.entities import NerAdapter, NerBatchAdapter, TextEntity
from redactor.schemas.formats import FileInspection
from redactor.schemas.persistence import Artifact, Task
from redactor.schemas.tabular import CsvRowPair
from redactor.schemas.verification import ResidualCheck, VerificationCheck
from redactor.utils.constants import (
    FIELD_PERSON_NAME,
    FIELD_TEXT,
    JUDGE_MAXIMUM_COLLECTED_RESIDUALS,
    REQUIRED_VERIFICATION_CHECKS,
    STEP_ANALYZE,
    STEP_INSPECT,
    VERIFICATION_PASS,
)
from redactor.utils.errors import (
    ERROR_ARTIFACT_CORRUPT,
    ERROR_CLINICAL_CHANGED,
    ERROR_COVERAGE,
    ERROR_REPLACEMENT,
    ERROR_STRUCTURE,
)
from redactor.verification.batches import batch_verifier, row_batches
from redactor.verification.headers import verify_column_headers
from redactor.verification.reader import read_csv_rows
from redactor.verification.residuals import verify_residual_entities
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
    verification_batch: NerBatchAdapter | None = None,
    judge_residuals: list[ResidualCheck] | None = None,
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
    read_evidence = make_row_evidence(policies, task.input_sha256)
    # Typed fast path: FIELD_TEXT and FIELD_PERSON_NAME cells take the text
    # findings path below, mirroring how rewrite routes those columns.
    typed_columns = {
        column.index: typed_column_operations(column, mapping_key)
        for column in policies
        if column.kind not in (FIELD_TEXT, FIELD_PERSON_NAME)
    }
    detector = detection_adapter(
        connection,
        task,
        settings=settings,
        mapping_key=mapping_key,
        local_ner=local_ner,
    )
    find_text = make_text_finder(
        detector,
        maximum_entries=settings.local.ner_cache_entries,
        maximum_text_characters=settings.local.ner_cache_characters,
    )
    maximum = settings.resources.max_record_bytes
    prepare_observation = observation_preparer(mapping_key)
    counts: Counter[str] = Counter()
    cells = records = 0
    observations: OrderedDict[str, tuple[TextEntity, ...]] = OrderedDict()
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
        pairs = _matching_rows(original, rewritten, len(policies))
        for batch in row_batches(pairs):
            residual_checks: list[ResidualCheck] = []
            for before, after in batch:
                number = records + 1
                evidence = read_evidence(before, number)
                context = row_context(
                    evidence,
                    lookup,
                    analysis_id,
                    task.input_sha256,
                    number,
                    mapping_key,
                    snapshot.maximum_date_shift_days,
                    observation_reader=prepare_observation,
                )
                for column in policies:
                    value = before[column.index]
                    cells += 1
                    if column.kind not in (FIELD_TEXT, FIELD_PERSON_NAME):
                        assess, replace = typed_columns[column.index]
                        replacing = assess(value)
                        replacement = replace(value, context) if replacing else value
                        if replacing and replacement == value:
                            raise ValueError(ERROR_REPLACEMENT)
                        if after[column.index] != replacement:
                            raise ValueError(
                                ERROR_REPLACEMENT
                                if replacing
                                else ERROR_CLINICAL_CHANGED
                            )
                        if replacing:
                            counts[column.kind] += 1
                        continue
                    findings = (
                        find_text(value, context.patient_name, context.provider_name)
                        if column.kind == FIELD_TEXT and value.strip()
                        else cell_findings(
                            value,
                            column,
                            detector,
                            patient_name=context.patient_name,
                            provider_name=context.provider_name,
                        )
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
                        output_ner=_verified_output_entities,
                        collect=residual_checks.append,
                    )
                    counts.update(edit.kind for edit in expected)
                records = number
            # Bounded collection for optional hosted judging; verdicts never
            # depend on it, and the cap bounds memory on very large files.
            if judge_residuals is not None and residual_checks:
                capacity = JUDGE_MAXIMUM_COLLECTED_RESIDUALS - len(judge_residuals)
                if capacity > 0:
                    judge_residuals.extend(residual_checks[:capacity])
            verifier = batch_verifier(
                residual_checks,
                local_ner,
                verification_batch,
                observations,
                maximum_entries=settings.local.ner_cache_entries,
                maximum_text_characters=settings.local.ner_cache_characters,
            )
            for check in residual_checks:
                verify_residual_entities(check, verifier)
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


def _matching_rows(
    original: Iterator[tuple[str, ...]],
    rewritten: Iterator[tuple[str, ...]],
    width: int,
) -> Iterator[CsvRowPair]:
    for before, after in zip_longest(original, rewritten):
        if before is None or after is None or not len(before) == len(after) == width:
            raise ValueError(ERROR_COVERAGE)
        yield before, after


def _verified_output_entities(text: str) -> tuple[TextEntity, ...]:
    """Saved text already passed exact edits and independent deterministic scans.

    Statistical evidence comes from the complete original text. Every unedited
    byte is identical, and each saved replacement was independently recomputed.
    Unique pseudonyms therefore do not require another statistical inference.
    """
    return ()
