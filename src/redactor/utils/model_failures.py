"""Translate provider errors into safe codes and bounded retry delays."""

import time
from email.utils import parsedate_to_datetime

import httpx
from openai import APIConnectionError

from redactor.schemas.provider import ModelFailure
from redactor.utils.constants import HTTP_RETRY_AFTER_HEADER
from redactor.utils.errors import (
    ERROR_MODEL_AUTH,
    ERROR_MODEL_REQUEST,
    ERROR_MODEL_RESPONSE,
    ERROR_MODEL_TRANSIENT,
)


def classify_model_error(error: Exception) -> ModelFailure:
    if isinstance(error, APIConnectionError):
        cause = error.__cause__
        if isinstance(cause, ValueError) and str(cause) == ERROR_MODEL_RESPONSE:
            return ModelFailure(reason_code=ERROR_MODEL_RESPONSE)
        if isinstance(cause, httpx.HTTPStatusError):
            status = cause.response.status_code
            if status in (401, 403):
                return ModelFailure(reason_code=ERROR_MODEL_AUTH)
            if status in (408, 409, 429) or status >= 500:
                return ModelFailure(
                    reason_code=ERROR_MODEL_TRANSIENT,
                    retry_after_seconds=_retry_after_seconds(cause.response),
                )
            return ModelFailure(reason_code=ERROR_MODEL_REQUEST)
        return ModelFailure(reason_code=ERROR_MODEL_TRANSIENT)
    if isinstance(error, (TimeoutError, httpx.HTTPError)):
        return ModelFailure(reason_code=ERROR_MODEL_TRANSIENT)
    return ModelFailure(reason_code=ERROR_MODEL_RESPONSE)


def _retry_after_seconds(response: httpx.Response) -> float:
    """Read the server's minimum wait; the retry loop applies exponential backoff."""
    value = response.headers.get(HTTP_RETRY_AFTER_HEADER)
    if value is None:
        return 0
    try:
        delay = float(value)
        return max(0, delay) if delay < float("inf") else float("inf")
    except ValueError:
        try:
            return max(0, parsedate_to_datetime(value).timestamp() - time.time())
        except (ValueError, TypeError, OverflowError):
            return 0
