"""Convert exceptions to registered failure codes without exposing input text."""

from redactor.utils.errors import (
    ERROR_PROCESSING,
    FAILURE_CODES,
    VERIFICATION_REASON_CODES,
)


def failure_reason(error: Exception) -> str:
    return next(
        (
            code
            for code in (*FAILURE_CODES, *VERIFICATION_REASON_CODES)
            if error.args == (code,)
        ),
        ERROR_PROCESSING,
    )
