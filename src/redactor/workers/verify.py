"""Accept a verdict for saved bytes and route failures to quarantine."""

import sqlite3

from redactor.persistence.files.registration import prepare_successor
from redactor.persistence.files.results import accepted_artifact, write_step_result
from redactor.schemas.configuration import PipelineSettings
from redactor.schemas.entities import NerAdapter
from redactor.schemas.persistence import Task
from redactor.schemas.pipeline import StepResult
from redactor.schemas.verification import VerificationCheck
from redactor.utils.constants import (
    CHECK_COVERAGE,
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
from redactor.verification.verdict import conclude_verification


def verify_task(
    connection: sqlite3.Connection,
    task: Task,
    *,
    settings: PipelineSettings,
    mapping_key: bytes,
    local_ner: NerAdapter,
    resolution_task_id: str,
) -> StepResult:
    producer = prepare_successor(connection, task, STEP_REWRITE)
    artifact = accepted_artifact(connection, producer.task_id)
    context = verification_context(connection, task, resolution_task_id, mapping_key)
    try:
        checks = verify_csv(
            connection,
            task,
            artifact,
            settings=settings,
            mapping_key=mapping_key,
            local_ner=local_ner,
            resolution_task_id=resolution_task_id,
        )
    except Exception as error:
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
    verdict = conclude_verification(context, producer.task_id, artifact, checks)
    step = STEP_PUBLISH if verdict.status == VERIFICATION_PASS else STEP_QUARANTINE
    return StepResult(
        artifact=write_step_result(connection, task, verdict),
        successors=(prepare_successor(connection, task, step),),
    )
