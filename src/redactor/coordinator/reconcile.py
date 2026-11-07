"""Reconcile every inventoried file with exactly one accepted terminal outcome."""

import sqlite3

from redactor.persistence.database import state_directory
from redactor.persistence.files.artifacts import inspect_artifact
from redactor.persistence.files.checkpoints import latest_checkpoint
from redactor.persistence.files.reports import replace_report
from redactor.persistence.files.results import read_step_result
from redactor.persistence.queue.tasks import get_task
from redactor.persistence.runs.inventory import file_step
from redactor.persistence.runs.manifests import read_manifest
from redactor.policy.keys import evidence_key
from redactor.schemas.analysis import FileAnalysis
from redactor.schemas.inventory import PreparedRun
from redactor.schemas.outcomes import FileOutcome
from redactor.schemas.reporting import FileReport, RunReport
from redactor.schemas.verification import VerificationVerdict
from redactor.utils.configuration import key_fingerprint
from redactor.utils.constants import (
    OUTCOME_PUBLISHED,
    OUTCOME_QUARANTINED,
    OUTPUT_DIRECTORY,
    REPORT_FILENAME,
    RUN_LOG_FILENAME,
    STATUS_SUCCEEDED,
    STEP_ANALYZE,
    STEP_PUBLISH,
    STEP_QUARANTINE,
    STEP_REWRITE,
    STEP_VERIFY,
)
from redactor.utils.errors import ERROR_ARTIFACT_CORRUPT, ERROR_PIPELINE_BLOCKED
from redactor.utils.filesystem import sync_directory


def reconcile_run(
    connection: sqlite3.Connection, run: PreparedRun, mapping_key: bytes
) -> RunReport:
    manifest = read_manifest(run.manifest, key_fingerprint(mapping_key))
    reports: list[FileReport] = []
    for source in manifest.files:
        terminals = connection.execute(
            "SELECT task_id FROM tasks WHERE processing_version = ? "
            "AND input_path = ? AND step IN (?, ?) AND status = ?",
            (
                run.manifest.sha256,
                str(source.input_path),
                STEP_PUBLISH,
                STEP_QUARANTINE,
                STATUS_SUCCEEDED,
            ),
        ).fetchall()
        if len(terminals) != 1:
            raise ValueError(ERROR_PIPELINE_BLOCKED)
        terminal = get_task(connection, terminals[0]["task_id"])
        outcome = read_step_result(
            connection,
            terminal.task_id,
            FileOutcome,
            encryption_key=mapping_key,
        )
        if inspect_artifact(outcome.artifact.path, persist=False) != outcome.artifact:
            raise ValueError(ERROR_ARTIFACT_CORRUPT)
        analysis = read_step_result(
            connection,
            file_step(connection, run.manifest, source, STEP_ANALYZE).task_id,
            FileAnalysis,
            encryption_key=mapping_key,
        )
        verify = connection.execute(
            "SELECT task_id FROM tasks WHERE processing_version = ? "
            "AND input_path = ? AND step = ? AND status = ?",
            (
                run.manifest.sha256,
                str(source.input_path),
                STEP_VERIFY,
                STATUS_SUCCEEDED,
            ),
        ).fetchone()
        judge_degradation = None
        if verify is not None:
            verdict = read_step_result(
                connection, verify["task_id"], VerificationVerdict
            )
            judge_degradation = verdict.judge_degradation
        rewrite = file_step(connection, run.manifest, source, STEP_REWRITE)
        checkpoint = latest_checkpoint(connection, rewrite.task_id)
        applied = checkpoint.counts if checkpoint else {}
        usage = connection.execute(
            "SELECT COALESCE(sum(input_tokens), 0), COALESCE(sum(output_tokens), 0), "
            "COALESCE(sum(COALESCE(charged_nanos, reserved_nanos)), 0) "
            "FROM model_attempts JOIN tasks USING(task_id) "
            "WHERE processing_version = ? AND input_path = ?",
            (run.manifest.sha256, str(source.input_path)),
        ).fetchone()
        duration = connection.execute(
            "SELECT COALESCE(sum(max(0, (julianday(finished_at) - "
            "julianday(started_at)) * 86400)), 0) "
            "FROM attempts JOIN tasks USING(task_id) "
            "WHERE processing_version = ? AND input_path = ?",
            (run.manifest.sha256, str(source.input_path)),
        ).fetchone()[0]
        reports.append(
            FileReport(
                file_id=evidence_key(
                    mapping_key,
                    source.relative_path.as_posix(),
                    namespace=REPORT_FILENAME,
                ),
                input_sha256=source.sha256,
                output_sha256=outcome.artifact.sha256,
                actual_type=analysis.file_type,
                status=outcome.status,
                reason=outcome.reason,
                records=analysis.record_count,
                detected=analysis.counts,
                applied=applied,
                confirmed=applied if outcome.status == OUTCOME_PUBLISHED else {},
                duration_seconds=round(duration, 3),
                input_tokens=usage[0],
                output_tokens=usage[1],
                cost_bound_nanos=usage[2],
                judge_degradation=judge_degradation,
            )
        )
    report = RunReport(
        run_id=run.manifest.sha256,
        complete=True,
        inventoried=len(manifest.files),
        published=sum(item.status == OUTCOME_PUBLISHED for item in reports),
        quarantined=sum(item.status == OUTCOME_QUARANTINED for item in reports),
        files=tuple(reports),
    )
    output = state_directory(connection).parent / OUTPUT_DIRECTORY
    replace_report(output / REPORT_FILENAME, report.model_dump_json(indent=2).encode())
    replace_report(
        output / RUN_LOG_FILENAME,
        b"".join((item.model_dump_json() + "\n").encode() for item in reports),
    )
    cleanup_staged_files(connection, run.manifest.sha256)
    return report


def cleanup_staged_files(
    connection: sqlite3.Connection, processing_version: str
) -> None:
    rows = connection.execute(
        "SELECT task_id FROM tasks WHERE processing_version = ? AND step IN (?, ?)",
        (processing_version, STEP_REWRITE, STEP_QUARANTINE),
    ).fetchall()
    for row in rows:
        task = get_task(connection, row["task_id"])
        if task.temporary_directory is not None and task.temporary_directory.exists():
            for path in task.temporary_directory.glob("*.part"):
                path.unlink()
            sync_directory(task.temporary_directory)
