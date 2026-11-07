"""Accept a verdict for saved bytes and route failures to quarantine."""

import io
import sqlite3

import httpx

from redactor.agents.judge.evidence import SavedImage, build_judge_evidence
from redactor.agents.judge.findings import apply_judge_findings
from redactor.agents.judge.judge import judge_saved_evidence
from redactor.formats.images import read_image_frames
from redactor.persistence.files.registration import prepare_successor
from redactor.persistence.files.results import (
    accepted_artifact,
    read_step_result,
    write_step_result,
)
from redactor.schemas.configuration import PipelineSettings
from redactor.schemas.entities import NerAdapter, NerBatchAdapter
from redactor.schemas.formats import FileInspection
from redactor.schemas.persistence import Artifact, Task
from redactor.schemas.pipeline import StepResult
from redactor.schemas.verification import ResidualCheck, VerificationCheck
from redactor.utils.constants import (
    CHECK_COVERAGE,
    IMAGE_FORMATS,
    JUDGE_SAVED_FRAME_MEDIA_TYPE,
    PIXEL_PNG_FORMAT,
    STEP_INSPECT,
    STEP_PUBLISH,
    STEP_QUARANTINE,
    STEP_REWRITE,
    VERIFICATION_FAIL,
    VERIFICATION_PASS,
)
from redactor.utils.errors import ERROR_PROCESSING, VERIFICATION_REASON_CODES
from redactor.utils.failures import failure_reason
from redactor.verification.context import verification_context
from redactor.verification.csv import verify_csv
from redactor.verification.images import verify_images
from redactor.verification.native import verify_native
from redactor.verification.verdict import conclude_verification


def verify_task(
    connection: sqlite3.Connection,
    task: Task,
    *,
    settings: PipelineSettings,
    mapping_key: bytes,
    local_ner: NerAdapter,
    resolution_task_id: str,
    verification_batch: NerBatchAdapter | None = None,
    transport: httpx.AsyncBaseTransport | None = None,
) -> StepResult:
    producer = prepare_successor(connection, task, STEP_REWRITE)
    artifact = accepted_artifact(connection, producer.task_id)
    context = verification_context(connection, task, resolution_task_id, mapping_key)
    judging = _judging_enabled(settings)
    judge_residuals: list[ResidualCheck] = []
    frames: tuple[SavedImage, ...] = ()
    failed_locally = False
    try:
        inspection = read_step_result(
            connection,
            prepare_successor(connection, task, STEP_INSPECT).task_id,
            FileInspection,
            encryption_key=mapping_key,
        )
        if inspection.file_type in IMAGE_FORMATS:
            checks = verify_images(
                connection,
                task,
                artifact,
                settings=settings,
                mapping_key=mapping_key,
                local_ner=local_ner,
            )
            if judging and settings.verification.judge_vision:
                frames = _saved_frames(artifact, settings)
        elif inspection.csv_layout is not None:
            checks = verify_csv(
                connection,
                task,
                artifact,
                settings=settings,
                mapping_key=mapping_key,
                local_ner=local_ner,
                resolution_task_id=resolution_task_id,
                verification_batch=verification_batch,
                judge_residuals=judge_residuals if judging else None,
            )
        else:
            checks = verify_native(
                connection,
                task,
                artifact,
                inspection,
                settings=settings,
                mapping_key=mapping_key,
                local_ner=local_ner,
                resolution_task_id=resolution_task_id,
                judge_residuals=judge_residuals if judging else None,
            )
    except Exception as error:
        failed_locally = True
        reason = failure_reason(error)
        checks = (
            VerificationCheck(
                kind=CHECK_COVERAGE,
                status=VERIFICATION_FAIL,
                expected=1,
                checked=0,
                unassessed=1,
                reason_code=reason
                if reason in VERIFICATION_REASON_CODES
                else ERROR_PROCESSING,
            ),
        )
    degradation: str | None = None
    if judging and not failed_locally:
        # The judge supplements local checks that already ran. Any judge
        # failure degrades to the local verdict; it can never weaken it.
        try:
            evidence = build_judge_evidence(judge_residuals, images=frames)
            outcome = judge_saved_evidence(
                connection,
                task,
                evidence,
                f"judge:{task.input_sha256}",
                settings=settings,
                mapping_key=mapping_key,
                transport=transport,
            )
            application = apply_judge_findings(checks, outcome)
            checks = application.checks
            if application.degradation is not None:
                degradation = application.degradation.reason_code
        except Exception as error:
            degradation = failure_reason(error)
    verdict = conclude_verification(
        context,
        producer.task_id,
        artifact,
        checks,
        judge_degradation=degradation,
    )
    step = STEP_PUBLISH if verdict.status == VERIFICATION_PASS else STEP_QUARANTINE
    return StepResult(
        artifact=write_step_result(connection, task, verdict),
        successors=(prepare_successor(connection, task, step),),
    )


def _judging_enabled(settings: PipelineSettings) -> bool:
    """Every disable switch keeps judging silent; local mode never calls out."""
    return (
        settings.remote.enabled
        and settings.verification.judge_enabled
        and bool(settings.verification.judge_model)
    )


def _saved_frames(
    artifact: Artifact, settings: PipelineSettings
) -> tuple[SavedImage, ...]:
    """Encode the saved output frames once as bounded portable PNG evidence."""
    frames: list[SavedImage] = []
    for image in read_image_frames(artifact.path, settings.resources):
        stream = io.BytesIO()
        image.save(stream, format=PIXEL_PNG_FORMAT)
        frames.append((stream.getvalue(), image.size, JUDGE_SAVED_FRAME_MEDIA_TYPE))
    return tuple(frames)
