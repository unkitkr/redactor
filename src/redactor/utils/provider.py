"""Functional provider entry point with durable replay and local fallback decisions."""

import asyncio
import hmac
import json
import os
import sqlite3
from collections.abc import Mapping

import httpx
from pydantic import BaseModel

from redactor.persistence.models.decisions import (
    read_model_decision,
    save_model_decision,
)
from redactor.persistence.queue.tasks import require_attempt
from redactor.schemas.configuration import PipelineSettings
from redactor.schemas.persistence import Task
from redactor.schemas.provider import ModelDecision, ModelRequest
from redactor.utils.configuration import key_fingerprint, processing_fingerprint
from redactor.utils.constants import (
    JSON_SEPARATORS,
    MODEL_KEY_ENVIRONMENT,
    MODEL_LOCAL,
    MODEL_PURPOSE_JUDGE,
    MODEL_REQUEST_CONTEXT,
)
from redactor.utils.errors import (
    ERROR_MODEL_CONFIGURATION,
    ERROR_MODEL_DISABLED,
    ERROR_MODEL_INPUT,
)
from redactor.utils.model_pricing import select_pricing
from redactor.utils.provider_runtime import run_model_request


def request_json(
    connection: sqlite3.Connection,
    claimed: Task,
    settings: PipelineSettings,
    request: ModelRequest,
    schema: type[BaseModel],
    mapping_key: bytes,
    *,
    environment: Mapping[str, str] | None = None,
    transport: httpx.AsyncBaseTransport | None = None,
) -> ModelDecision:
    """Return validated JSON or a durable reason to use a local adapter.

    This function performs no local inference and cannot authorize publication.
    The optional HTTP transport is the test boundary; production uses the SDK.
    """
    require_attempt(connection, claimed)
    key_fingerprint(mapping_key)
    environment = os.environ if environment is None else environment
    if not _input_fits(request, settings.remote.max_input_bytes):
        return ModelDecision(backend=MODEL_LOCAL, reason_code=ERROR_MODEL_INPUT)
    identity = json.dumps(
        (
            claimed.task_id,
            processing_fingerprint(settings),
            request.model_dump(),
            schema.model_json_schema(),
        ),
        sort_keys=True,
        separators=JSON_SEPARATORS,
    ).encode()
    request_key = hmac.digest(
        mapping_key, MODEL_REQUEST_CONTEXT + identity, "sha256"
    ).hex()
    cached = read_model_decision(connection, request_key, mapping_key)
    if cached is not None:
        return cached

    reason = None
    if not settings.remote.enabled or (
        request.purpose == MODEL_PURPOSE_JUDGE
        and not settings.verification.judge_enabled
    ):
        reason = ERROR_MODEL_DISABLED
    api_key = environment.get(MODEL_KEY_ENVIRONMENT, "")
    if reason is None and (not api_key or not settings.remote.base_url):
        reason = ERROR_MODEL_CONFIGURATION
    try:
        pricing = select_pricing(settings, request)
    except ValueError as error:
        reason = reason or str(error)
    if reason is not None:
        return save_model_decision(
            connection,
            claimed,
            request_key,
            ModelDecision(backend=MODEL_LOCAL, reason_code=reason),
            mapping_key,
            settings.remote,
        )
    return asyncio.run(
        run_model_request(
            connection,
            claimed,
            settings.remote,
            request,
            request_key,
            pricing,
            schema,
            mapping_key,
            api_key,
            transport,
        )
    )


def _input_fits(request: ModelRequest, maximum_bytes: int) -> bool:
    if len(request.system_prompt) + len(request.input_text) > maximum_bytes:
        return False
    return len(request.system_prompt.encode()) + len(request.input_text.encode()) <= (
        maximum_bytes
    )
