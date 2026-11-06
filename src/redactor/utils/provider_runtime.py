"""Bound attempts, elapsed time and billing before accepting a remote answer."""

import asyncio
import random
import sqlite3
import time

import httpx
from openai import APIConnectionError
from pydantic import BaseModel

from redactor.persistence.models.budget import reserve_attempt, settle_attempt
from redactor.persistence.models.decisions import save_model_decision
from redactor.schemas.configuration import RemoteSettings
from redactor.schemas.persistence import Task
from redactor.schemas.provider import (
    ModelDecision,
    ModelFailure,
    ModelPricing,
    ModelRequest,
    ModelUnavailable,
    ModelUsage,
)
from redactor.utils.constants import (
    MODEL_FINISH_STOP,
    MODEL_LOCAL,
    MODEL_REMOTE,
    MODEL_RETRY_BASE_SECONDS,
)
from redactor.utils.errors import (
    ERROR_MODEL_AUTH,
    ERROR_MODEL_BUDGET,
    ERROR_MODEL_CONFIGURATION,
    ERROR_MODEL_PRICE_BOUND,
    ERROR_MODEL_RESPONSE,
    ERROR_MODEL_TRANSIENT,
)
from redactor.utils.model_failures import classify_model_error
from redactor.utils.model_pricing import (
    currency_nanos,
    maximum_request_cost,
    token_cost,
)
from redactor.utils.model_transport import open_model_client, request_completion


async def run_model_request(
    connection: sqlite3.Connection,
    claimed: Task,
    settings: RemoteSettings,
    request: ModelRequest,
    request_key: str,
    pricing: ModelPricing,
    schema: type[BaseModel],
    mapping_key: bytes,
    api_key: str,
    transport: httpx.AsyncBaseTransport | None,
) -> ModelDecision:
    maximum_cost = maximum_request_cost(pricing, request, settings.max_output_tokens)
    budget = currency_nanos(settings.budget_usd)
    deadline = time.monotonic() + settings.deadline_seconds
    failure = ModelFailure(reason_code=ERROR_MODEL_TRANSIENT)
    had_transient_failure = False
    try:
        async with open_model_client(settings, api_key, transport) as client:
            for attempt_index in range(settings.max_attempts):
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                reservation = reserve_attempt(
                    connection, claimed, request_key, maximum_cost, budget, settings
                )
                if isinstance(reservation, ModelUnavailable):
                    failure = ModelFailure(reason_code=reservation.reason_code)
                    break
                try:
                    async with asyncio.timeout(
                        min(remaining, settings.timeout_seconds)
                    ):
                        completion = await request_completion(
                            client, settings, pricing.model, request
                        )
                except (
                    APIConnectionError,
                    httpx.HTTPError,
                    TimeoutError,
                    ValueError,
                ) as error:
                    settle_attempt(connection, claimed, reservation, None)
                    failure = classify_model_error(error)
                else:
                    receipt = completion.usage
                    usage = None
                    if (
                        receipt is not None
                        and min(receipt.prompt_tokens, receipt.completion_tokens) >= 0
                    ):
                        usage = ModelUsage(
                            input_tokens=receipt.prompt_tokens,
                            output_tokens=receipt.completion_tokens,
                            cost_nanos=token_cost(
                                pricing,
                                receipt.prompt_tokens,
                                receipt.completion_tokens,
                            ),
                        )
                    settle_attempt(connection, claimed, reservation, usage)
                    if usage is not None and usage.cost_nanos > maximum_cost:
                        failure = ModelFailure(reason_code=ERROR_MODEL_PRICE_BOUND)
                        break
                    try:
                        if len(completion.choices) != 1:
                            raise ValueError(ERROR_MODEL_RESPONSE)
                        choice = completion.choices[0]
                        if (
                            choice.finish_reason != MODEL_FINISH_STOP
                            or choice.message.refusal
                            or choice.message.tool_calls
                            or choice.message.content is None
                        ):
                            raise ValueError(ERROR_MODEL_RESPONSE)
                        validated = schema.model_validate_json(
                            choice.message.content, strict=True
                        )
                    except ValueError:
                        failure = ModelFailure(reason_code=ERROR_MODEL_RESPONSE)
                    else:
                        return save_model_decision(
                            connection,
                            claimed,
                            request_key,
                            ModelDecision(
                                backend=MODEL_REMOTE,
                                payload=validated.model_dump(mode="json"),
                            ),
                            mapping_key,
                            settings,
                        )
                if failure.reason_code != ERROR_MODEL_TRANSIENT:
                    break
                had_transient_failure = True
                delay = max(
                    failure.retry_after_seconds,
                    MODEL_RETRY_BASE_SECONDS * (2**attempt_index)
                    + random.random() / 10,
                )
                if attempt_index + 1 == settings.max_attempts or (
                    time.monotonic() + delay >= deadline
                ):
                    break
                await asyncio.sleep(delay)
    except ValueError as error:
        if str(error) != ERROR_MODEL_CONFIGURATION:
            raise
        failure = ModelFailure(reason_code=ERROR_MODEL_CONFIGURATION)

    return save_model_decision(
        connection,
        claimed,
        request_key,
        ModelDecision(backend=MODEL_LOCAL, reason_code=failure.reason_code),
        mapping_key,
        settings,
        transient_failure=had_transient_failure,
        disable_remote=failure.reason_code
        in (ERROR_MODEL_AUTH, ERROR_MODEL_BUDGET, ERROR_MODEL_PRICE_BOUND),
    )
