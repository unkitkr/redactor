"""Integration through the real OpenAI SDK and a controlled HTTP boundary."""

import asyncio
import sqlite3
from decimal import Decimal
from pathlib import Path

import httpx

from redactor.persistence.files import register_file
from redactor.persistence.model_budget import accounted_cost, recover_model_attempts
from redactor.persistence.queue import claim_task, recover_interrupted
from redactor.schemas.configuration import PipelineSettings, RemoteSettings
from redactor.schemas.provider import ModelRequest, ModelUnavailable
from redactor.utils.constants import MODEL_RESPONSE_BYTES
from redactor.utils.errors import (
    ERROR_MODEL_AUTH,
    ERROR_MODEL_DISABLED,
    ERROR_MODEL_REQUEST,
    ERROR_MODEL_RESPONSE,
    ERROR_MODEL_TRANSIENT,
)
from redactor.utils.provider import request_json


def test_provider_retries_once_then_replays_without_another_call_or_charge(
    connection: sqlite3.Connection, source_file: Path
) -> None:
    register_file(connection, source_file, "analyze", "provider-replay-v1")
    claimed = claim_task(connection)
    assert claimed is not None
    settings = PipelineSettings(
        remote=RemoteSettings(
            base_url="https://model.example/v1",
            model="test-model",
            input_usd_per_million=Decimal("1"),
            output_usd_per_million=Decimal("1"),
        )
    )
    request = ModelRequest(
        purpose="detector",
        prompt_version="test-v1",
        system_prompt="Return JSON matching the requested structure.",
        input_text="Synthetic confidential input",
        context_id="unit-1",
    )
    calls = 0

    async def endpoint(http_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        assert http_request.url == "https://model.example/v1/chat/completions"
        if calls == 1:
            return httpx.Response(429, headers={"Retry-After": "0"})
        return _completion_response()

    transport = httpx.MockTransport(endpoint)
    decision = request_json(
        connection,
        claimed,
        settings,
        request,
        ModelUnavailable,
        bytes(range(32)),
        environment={"LLM_API_KEY": "test-key"},
        transport=transport,
    )
    assert decision.backend == "remote"
    assert decision.payload == {"reason_code": "synthetic-result"}
    assert calls == 2
    cost = accounted_cost(connection, claimed.processing_version)
    assert cost > 20_000  # The unknown first charge is still reserved.

    recover_interrupted(connection)
    recover_model_attempts(connection)
    resumed = claim_task(connection)
    assert resumed is not None
    replay = request_json(
        connection,
        resumed,
        settings.model_copy(
            update={"remote": settings.remote.model_copy(update={"enabled": False})}
        ),
        request,
        ModelUnavailable,
        bytes(range(32)),
        environment={},
        transport=transport,
    )
    assert replay == decision
    assert calls == 2
    assert accounted_cost(connection, resumed.processing_version) == cost


def test_provider_fails_closed_for_revocation_garbage_size_timeout_and_disable(
    connection: sqlite3.Connection, source_file: Path
) -> None:
    cases = (
        ("revoked", ERROR_MODEL_AUTH),
        ("garbage", ERROR_MODEL_RESPONSE),
        ("oversized", ERROR_MODEL_RESPONSE),
        ("schema", ERROR_MODEL_RESPONSE),
        ("compressed", ERROR_MODEL_RESPONSE),
        ("redirect", ERROR_MODEL_REQUEST),
        ("slow", ERROR_MODEL_TRANSIENT),
        ("disabled", ERROR_MODEL_DISABLED),
    )
    for case, reason in cases:
        version = f"provider-{case}-v1"
        register_file(connection, source_file, "analyze", version)
        claimed = claim_task(connection, processing_version=version)
        assert claimed is not None
        settings = PipelineSettings(
            remote=RemoteSettings(
                enabled=case != "disabled",
                base_url="https://model.example/v1",
                model="test-model",
                input_usd_per_million=Decimal("1"),
                output_usd_per_million=Decimal("1"),
                timeout_seconds=0.05,
                deadline_seconds=0.1,
            )
        )
        calls = 0

        async def endpoint(
            http_request: httpx.Request, scenario: str = case
        ) -> httpx.Response:
            nonlocal calls
            calls += 1
            if scenario == "revoked":
                return httpx.Response(401, content=b"must not be logged")
            if scenario == "garbage":
                return httpx.Response(200, content=b"not JSON")
            if scenario == "oversized":
                return httpx.Response(200, content=b"x" * (MODEL_RESPONSE_BYTES + 1))
            if scenario == "schema":
                payload = _completion_response().json()
                payload["choices"][0]["message"]["content"] = '{"unexpected":true}'
                return httpx.Response(200, json=payload)
            if scenario == "compressed":
                return httpx.Response(200, headers={"Content-Encoding": "gzip"})
            if scenario == "redirect":
                return httpx.Response(
                    302, headers={"Location": "https://elsewhere.test"}
                )
            await asyncio.sleep(1)
            return _completion_response()

        request = ModelRequest(
            purpose="detector",
            prompt_version="test-v1",
            system_prompt="Return JSON.",
            input_text="Synthetic input",
            context_id="unit-1",
        )
        decision = request_json(
            connection,
            claimed,
            settings,
            request,
            ModelUnavailable,
            bytes(range(32)),
            environment={"LLM_API_KEY": "test-key"},
            transport=httpx.MockTransport(endpoint),
        )
        assert decision.backend == "local", case
        assert decision.reason_code == reason, case
        assert calls == (0 if case == "disabled" else 1), case


def _completion_response() -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "id": "completion-test",
            "object": "chat.completion",
            "created": 0,
            "model": "test-model",
            "choices": [
                {
                    "index": 0,
                    "finish_reason": "stop",
                    "message": {
                        "role": "assistant",
                        "content": '{"reason_code":"synthetic-result"}',
                    },
                }
            ],
            "usage": {"prompt_tokens": 10, "completion_tokens": 10, "total_tokens": 20},
        },
    )
