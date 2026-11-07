"""Aggregate required evidence without letting a model waive a failed check."""

from collections.abc import Sequence

from redactor.schemas.persistence import Artifact
from redactor.schemas.verification import (
    VerificationCheck,
    VerificationContext,
    VerificationStatus,
    VerificationVerdict,
)
from redactor.utils.constants import (
    CHECK_PIXELS,
    REQUIRED_VERIFICATION_CHECKS,
    VERIFICATION_FAIL,
    VERIFICATION_PASS,
    VERIFICATION_UNKNOWN,
)
from redactor.utils.errors import (
    ERROR_VERIFICATION,
    ERROR_VERIFICATION_RECORD,
    VERIFICATION_REASON_CODES,
)


def conclude_verification(
    context: VerificationContext,
    producer_task_id: str,
    artifact: Artifact,
    checks: Sequence[VerificationCheck],
    *,
    judge_degradation: str | None = None,
) -> VerificationVerdict:
    required = set(REQUIRED_VERIFICATION_CHECKS)
    if context.has_pixels:
        required.add(CHECK_PIXELS)
    kinds = {check.kind for check in checks}
    if len(kinds) != len(checks):
        raise ValueError(ERROR_VERIFICATION_RECORD)
    if any(
        check.reason_code is not None
        and check.reason_code not in VERIFICATION_REASON_CODES
        for check in checks
    ):
        raise ValueError(ERROR_VERIFICATION_RECORD)

    status: VerificationStatus = VERIFICATION_PASS
    if not required.issubset(kinds):
        status = VERIFICATION_UNKNOWN
    for check in checks:
        if check.status == VERIFICATION_FAIL or check.failed:
            status = VERIFICATION_FAIL
        elif status != VERIFICATION_FAIL and (
            check.status != VERIFICATION_PASS
            or check.unassessed
            or check.checked != check.expected
            or check.reason_code is not None
        ):
            status = VERIFICATION_UNKNOWN

    return VerificationVerdict(
        context=context,
        producer_task_id=producer_task_id,
        artifact=artifact,
        checks=tuple(checks),
        status=status,
        judge_degradation=judge_degradation,
    )


def require_passing_verdict(verdict: VerificationVerdict) -> None:
    """Recompute the aggregate; never trust a serialized `status: pass` alone."""
    recomputed = conclude_verification(
        verdict.context, verdict.producer_task_id, verdict.artifact, verdict.checks
    )
    if verdict.status != VERIFICATION_PASS or recomputed.status != VERIFICATION_PASS:
        raise ValueError(ERROR_VERIFICATION)
