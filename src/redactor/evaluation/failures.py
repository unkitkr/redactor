"""Keep evaluation failure detail limited to registered, PHI-free codes."""

from redactor.utils.errors import MODEL_REASON_CODES
from redactor.utils.failures import failure_reason


def evaluation_failure(error: Exception) -> str:
    return next(
        (code for code in MODEL_REASON_CODES if error.args == (code,)),
        failure_reason(error),
    )
