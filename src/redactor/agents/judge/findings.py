"""Turn judge findings into additional failures without weakening any check."""

from collections.abc import Sequence

from redactor.schemas.judge import JudgeApplication, JudgeDegradation, JudgeOutcome
from redactor.schemas.verification import VerificationCheck
from redactor.utils.constants import (
    CHECK_RESIDUAL_PHI,
    JUDGE_FAILING_VERDICTS,
    VERIFICATION_FAIL,
)
from redactor.utils.errors import ERROR_RESIDUAL_PHI


def apply_judge_findings(
    checks: Sequence[VerificationCheck], outcome: JudgeOutcome
) -> JudgeApplication:
    """Judge results can only add failures; the local verdict otherwise stands.

    Leak, likely-leak and unsure findings fail closed: each adds one residual
    PHI failure to the residual check, creating it when no local check of that
    kind exists. A clean or degraded judge changes no check, and a degradation
    is returned separately for the caller to record in verdict or report data.
    """
    failing = sum(
        1 for finding in outcome.findings if finding.verdict in JUDGE_FAILING_VERDICTS
    )
    degradation = (
        JudgeDegradation(reason_code=outcome.reason_code)
        if outcome.reason_code is not None
        else None
    )
    if not failing:
        return JudgeApplication(checks=tuple(checks), degradation=degradation)
    updated: list[VerificationCheck] = []
    judged = False
    for check in checks:
        if check.kind == CHECK_RESIDUAL_PHI:
            judged = True
            check = check.model_copy(
                update={
                    "status": VERIFICATION_FAIL,
                    "failed": check.failed + failing,
                    "reason_code": check.reason_code or ERROR_RESIDUAL_PHI,
                }
            )
        updated.append(check)
    if not judged:
        updated.append(
            VerificationCheck(
                kind=CHECK_RESIDUAL_PHI,
                status=VERIFICATION_FAIL,
                expected=1,
                checked=1,
                failed=failing,
                reason_code=ERROR_RESIDUAL_PHI,
            )
        )
    return JudgeApplication(checks=tuple(updated), degradation=degradation)
