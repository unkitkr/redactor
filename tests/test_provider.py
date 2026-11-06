"""Integration through the real OpenAI SDK and a controlled HTTP boundary."""

import asyncio
import random
import sqlite3
import time
from decimal import Decimal
from pathlib import Path

import httpx
import pytest

from redactor.persistence.files.registration import register_file
from redactor.persistence.models.budget import accounted_cost, recover_model_attempts
from redactor.persistence.queue.tasks import claim_task, recover_interrupted
from redactor.schemas.configuration import PipelineSettings, RemoteSettings
from redactor.schemas.provider import ModelRequest, ModelUnavailable
from redactor.utils.constants import MODEL_RESPONSE_BYTES
from redactor.utils.errors import (
    ERROR_MODEL_AUTH,
    ERROR_MODEL_BUDGET,
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


def test_configured_backoff_honors_attempt_deadline_and_budget_limits(
    connection: sqlite3.Connection,
    source_file: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    delays: list[float] = []

    async def record_sleep(delay: float) -> None:
        delays.append(delay)

    def maximum_jitter(lower: float, upper: float) -> float:
        return upper

    # Only time and randomness are controlled; SDK, HTTP handling and SQLite run.
    monkeypatch.setattr(asyncio, "sleep", record_sleep)
    monkeypatch.setattr(random, "uniform", maximum_jitter)
    for scenario in ("attempts", "server_delay", "deadline", "budget"):
        delays.clear()
        version = f"provider-backoff-{scenario}"
        register_file(connection, source_file, "analyze", version)
        claimed = claim_task(connection, processing_version=version)
        assert claimed is not None
        settings = PipelineSettings(
            remote=RemoteSettings(
                base_url="https://model.example/v1",
                model="test-model",
                input_usd_per_million=Decimal("1"),
                output_usd_per_million=Decimal("1"),
                max_attempts=4,
                retry_initial_seconds=1,
                retry_max_seconds=2,
                deadline_seconds=45,
                budget_usd=Decimal("0.003" if scenario == "budget" else "3"),
            )
        )
        calls = 0

        async def endpoint(
            http_request: httpx.Request, case: str = scenario
        ) -> httpx.Response:
            nonlocal calls
            calls += 1
            retry_after = (
                "60" if case == "deadline" else "3" if case == "server_delay" else "0"
            )
            return httpx.Response(429, headers={"Retry-After": retry_after})

        decision = request_json(
            connection,
            claimed,
            settings,
            ModelRequest(
                purpose="detector",
                prompt_version="test-v1",
                system_prompt="Return JSON.",
                input_text="Synthetic input",
                context_id="unit-1",
            ),
            ModelUnavailable,
            bytes(range(32)),
            environment={"LLM_API_KEY": "test-key"},
            transport=httpx.MockTransport(endpoint),
        )
        assert decision.backend == "local"
        assert calls == (1 if scenario in ("deadline", "budget") else 4)
        if scenario == "attempts":
            assert delays == [1, 2, 2]
        elif scenario == "server_delay":
            assert delays == [3, 3, 3]  # The server's minimum can exceed our cap.
        elif scenario == "deadline":
            assert delays == []  # Never retry early to squeeze inside the deadline.
        else:
            assert delays == [1]
        expected_reason = (
            ERROR_MODEL_BUDGET if scenario == "budget" else ERROR_MODEL_TRANSIENT
        )
        assert decision.reason_code == expected_reason
        assert accounted_cost(connection, version) <= int(
            settings.remote.budget_usd * 10**9
        )


def test_interrupted_request_keeps_attempt_limit_and_backoff_progress(
    connection: sqlite3.Connection,
    source_file: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    delays: list[float] = []

    async def record_sleep(delay: float) -> None:
        delays.append(delay)

    def maximum_jitter(lower: float, upper: float) -> float:
        return upper

    monkeypatch.setattr(asyncio, "sleep", record_sleep)
    monkeypatch.setattr(random, "uniform", maximum_jitter)
    register_file(connection, source_file, "analyze", "provider-interruption-v1")
    claimed = claim_task(connection)
    assert claimed is not None
    settings = PipelineSettings(
        remote=RemoteSettings(
            base_url="https://model.example/v1",
            model="test-model",
            input_usd_per_million=Decimal("1"),
            output_usd_per_million=Decimal("1"),
            max_attempts=4,
            retry_initial_seconds=1,
            retry_max_seconds=8,
        )
    )
    request = ModelRequest(
        purpose="detector",
        prompt_version="test-v1",
        system_prompt="Return JSON.",
        input_text="Synthetic input",
        context_id="unit-1",
    )
    calls = 0

    async def endpoint(http_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 2:
            # Leave a reserved request and unfinished task, as a dead worker does.
            raise asyncio.CancelledError
        return httpx.Response(429, headers={"Retry-After": "0"})

    transport = httpx.MockTransport(endpoint)
    with pytest.raises(asyncio.CancelledError):
        request_json(
            connection,
            claimed,
            settings,
            request,
            ModelUnavailable,
            bytes(range(32)),
            environment={"LLM_API_KEY": "test-key"},
            transport=transport,
        )
    assert delays == [1]
    recover_interrupted(connection)
    recover_model_attempts(connection)
    resumed = claim_task(connection)
    assert resumed is not None
    decision = request_json(
        connection,
        resumed,
        settings,
        request,
        ModelUnavailable,
        bytes(range(32)),
        environment={"LLM_API_KEY": "test-key"},
        transport=transport,
    )
    assert decision.backend == "local"
    assert calls == 4
    assert delays == [1, 4]
    assert connection.execute("SELECT count(*) FROM model_attempts").fetchone()[0] == 4


def test_retry_wait_and_request_deadline_survive_interruption(
    connection: sqlite3.Connection,
    source_file: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = [1_000.0]
    monkeypatch.setattr(time, "time", lambda: clock[0])
    for scenario in ("resume_wait", "expired_deadline"):
        version = f"provider-window-{scenario}"
        register_file(connection, source_file, "analyze", version)
        claimed = claim_task(connection, processing_version=version)
        assert claimed is not None
        settings = PipelineSettings(
            remote=RemoteSettings(
                base_url="https://model.example/v1",
                model="test-model",
                input_usd_per_million=Decimal("1"),
                output_usd_per_million=Decimal("1"),
                deadline_seconds=10,
            )
        )
        request = ModelRequest(
            purpose="detector",
            prompt_version="test-v1",
            system_prompt="Return JSON.",
            input_text="Synthetic input",
            context_id="unit-1",
        )
        delays: list[float] = []

        async def sleep_or_interrupt(delay: float, waits: list[float] = delays) -> None:
            waits.append(delay)
            if len(waits) == 1:
                raise asyncio.CancelledError
            clock[0] += delay

        monkeypatch.setattr(asyncio, "sleep", sleep_or_interrupt)
        calls = 0

        async def endpoint(http_request: httpx.Request) -> httpx.Response:
            nonlocal calls
            calls += 1
            if calls == 1:
                return httpx.Response(429, headers={"Retry-After": "4"})
            return _completion_response()

        transport = httpx.MockTransport(endpoint)
        with pytest.raises(asyncio.CancelledError):
            request_json(
                connection,
                claimed,
                settings,
                request,
                ModelUnavailable,
                bytes(range(32)),
                environment={"LLM_API_KEY": "test-key"},
                transport=transport,
            )
        clock[0] += 1 if scenario == "resume_wait" else 20
        recover_interrupted(connection)
        recover_model_attempts(connection)
        resumed = claim_task(connection, processing_version=version)
        assert resumed is not None
        decision = request_json(
            connection,
            resumed,
            settings,
            request,
            ModelUnavailable,
            bytes(range(32)),
            environment={"LLM_API_KEY": "test-key"},
            transport=transport,
        )
        if scenario == "resume_wait":
            assert calls == 2 and decision.backend == "remote"
            assert delays == [4, 3]
        else:
            assert calls == 1 and decision.backend == "local"
            assert delays == [4]


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
