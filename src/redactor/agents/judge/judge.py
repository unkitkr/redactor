"""Review saved-output evidence through replayable remote judging or degrade."""

import sqlite3
from collections.abc import Mapping

import httpx
from pydantic import JsonValue

from redactor.agents.judge.prompts import judge_request
from redactor.agents.judge.runtime import vision_transport
from redactor.schemas.configuration import PipelineSettings
from redactor.schemas.judge import (
    JudgeAssessment,
    JudgeEvidence,
    JudgeFinding,
    JudgeOutcome,
)
from redactor.schemas.persistence import Task
from redactor.utils.constants import (
    JUDGE_PROMPT_VERSION,
    JUDGE_VISION_INPUT_BYTES,
    MODEL_REMOTE,
)
from redactor.utils.errors import ERROR_JUDGE_EVIDENCE, ERROR_MODEL_RESPONSE
from redactor.utils.provider import request_json


def judge_saved_evidence(
    connection: sqlite3.Connection,
    claimed: Task,
    evidence: JudgeEvidence,
    context_id: str,
    *,
    settings: PipelineSettings,
    mapping_key: bytes,
    environment: Mapping[str, str] | None = None,
    transport: httpx.AsyncBaseTransport | None = None,
) -> JudgeOutcome:
    """Return validated findings or a structured degradation code.

    The provider replays an accepted response before checking availability,
    which also covers a crash between saving a response and its use. A judge
    degradation never weakens the local verification verdict, and images are
    judged only when vision judging is enabled.
    """
    if not settings.verification.judge_vision:
        evidence = evidence.model_copy(update={"images": ()})
    if not evidence.items and not evidence.images:
        return JudgeOutcome(prompt_version=JUDGE_PROMPT_VERSION)
    request = judge_request(evidence, context_id)
    call_settings = settings
    call_transport = transport
    if evidence.images:
        call_settings = _vision_settings(settings)
        call_transport = vision_transport(transport)
    decision = request_json(
        connection,
        claimed,
        call_settings,
        request,
        JudgeAssessment,
        mapping_key,
        environment=environment,
        transport=call_transport,
    )
    if decision.backend == MODEL_REMOTE:
        findings = _validated_findings(evidence, decision.payload)
        if findings is None:
            return JudgeOutcome(
                reason_code=ERROR_JUDGE_EVIDENCE,
                prompt_version=request.prompt_version,
                receipt=decision.receipt,
            )
        return JudgeOutcome(
            findings=findings,
            prompt_version=request.prompt_version,
            receipt=decision.receipt,
        )
    return JudgeOutcome(
        reason_code=decision.reason_code or ERROR_MODEL_RESPONSE,
        prompt_version=request.prompt_version,
        receipt=decision.receipt,
    )


def _vision_settings(settings: PipelineSettings) -> PipelineSettings:
    """Image requests need a larger input bound; text judging keeps the default."""
    if settings.remote.max_input_bytes >= JUDGE_VISION_INPUT_BYTES:
        return settings
    remote = settings.remote.model_copy(
        update={"max_input_bytes": JUDGE_VISION_INPUT_BYTES}
    )
    return settings.model_copy(update={"remote": remote})


def _validated_findings(
    evidence: JudgeEvidence, payload: dict[str, JsonValue] | None
) -> tuple[JudgeFinding, ...] | None:
    """Accept findings only when every reference matches evidence actually sent."""
    sent = {item.reference for item in evidence.items}
    sent.update(image.reference for image in evidence.images)
    try:
        assessment = JudgeAssessment.model_validate(payload or {})
    except ValueError:
        return None
    if any(finding.reference not in sent for finding in assessment.findings):
        return None
    return assessment.findings
