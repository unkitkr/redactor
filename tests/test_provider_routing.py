"""OpenRouter requests use the same rate bounds as durable budget reservations."""

import json
import sqlite3
from decimal import Decimal
from pathlib import Path

import httpx

from redactor.persistence.files.registration import register_file
from redactor.persistence.models.budget import accounted_cost
from redactor.persistence.queue.tasks import claim_task
from redactor.schemas.configuration import (
    PipelineSettings,
    RemoteSettings,
    VerificationSettings,
)
from redactor.schemas.provider import ModelRequest, ModelUnavailable
from redactor.utils.constants import MAX_SQLITE_INTEGER
from redactor.utils.errors import ERROR_MODEL_PRICE_BOUND, ERROR_MODEL_RESPONSE
from redactor.utils.provider import request_json


def test_openrouter_routing_receipts_and_overcharge_fail_closed(
    connection: sqlite3.Connection, source_file: Path
) -> None:
    malformed_scenarios = (
        "invalid_cost",
        "cost_object",
        "huge_cost",
        "huge_input_tokens",
        "huge_output_tokens",
        "negative_tokens",
        "unrepresentable_token_cost",
    )
    for scenario in ("detector", "judge", "overcharge", *malformed_scenarios):
        version = f"openrouter-{scenario}"
        register_file(connection, source_file, "analyze", version)
        claimed = claim_task(connection, processing_version=version)
        assert claimed is not None
        settings = PipelineSettings(
            remote=RemoteSettings(
                enabled=True,
                provider="openrouter",
                base_url="https://openrouter.ai/api/v1",
                model="z-ai/glm-5.3-flash",
                reasoning_enabled=True,
                input_usd_per_million=Decimal("0.15"),
                output_usd_per_million=Decimal("0.50"),
                max_output_tokens=2048,
            ),
            verification=VerificationSettings(
                judge_model="separate-judge",
                input_usd_per_million=Decimal("0.25"),
                output_usd_per_million=Decimal("0.75"),
            ),
        )
        request = ModelRequest(
            purpose="judge" if scenario == "judge" else "detector",
            prompt_version="routing-test-v1",
            system_prompt="Return JSON.",
            input_text="Synthetic input",
            context_id="first",
        )
        calls = 0

        async def endpoint(
            http_request: httpx.Request, case: str = scenario
        ) -> httpx.Response:
            nonlocal calls
            calls += 1
            payload = json.loads(http_request.content)
            assert payload["model"] == (
                "separate-judge" if case == "judge" else "z-ai/glm-5.3-flash"
            )
            assert payload["provider"] == {
                "require_parameters": True,
                "max_price": {
                    "prompt": 0.25 if case == "judge" else 0.15,
                    "completion": 0.75 if case == "judge" else 0.5,
                    "request": 0,
                    "image": 0,
                },
            }
            assert payload["reasoning"] == {"enabled": True}
            assert payload["temperature"] == 0
            assert payload["max_tokens"] == 2048
            assert payload["response_format"] == {"type": "json_object"}
            reported_cost: object = 0.01 if case == "overcharge" else 0
            if case == "invalid_cost":
                reported_cost = "NaN"
            elif case == "cost_object":
                reported_cost = {"unexpected": "value"}
            elif case == "huge_cost":
                reported_cost = "1e100000000"
            input_tokens = output_tokens = 10
            if case == "huge_input_tokens":
                input_tokens = MAX_SQLITE_INTEGER + 1
            elif case == "huge_output_tokens":
                output_tokens = MAX_SQLITE_INTEGER + 1
            elif case == "negative_tokens":
                input_tokens = -1
            elif case == "unrepresentable_token_cost":
                output_tokens = MAX_SQLITE_INTEGER
            return httpx.Response(
                200,
                json={
                    "id": "synthetic-completion",
                    "object": "chat.completion",
                    "created": 0,
                    "model": "returned-model-version",
                    "provider": "Test Provider",
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
                    "usage": {
                        "prompt_tokens": input_tokens,
                        "completion_tokens": output_tokens,
                        "total_tokens": input_tokens + output_tokens,
                        "cost": reported_cost,
                    },
                },
            )

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
        assert calls == 1
        if scenario in malformed_scenarios:
            assert decision.backend == "local"
            assert decision.reason_code == ERROR_MODEL_RESPONSE
            assert decision.receipt is None
            assert accounted_cost(connection, version) > 0
            attempt = connection.execute(
                "SELECT status, charged_nanos FROM model_attempts WHERE task_id = ?",
                (claimed.task_id,),
            ).fetchone()
            assert attempt["status"] == "uncertain"
            assert attempt["charged_nanos"] is None
            continue
        assert decision.receipt is not None
        assert decision.receipt.returned_model == "returned-model-version"
        assert decision.receipt.provider == "Test Provider"
        assert decision.receipt.input_tokens == 10
        assert decision.receipt.output_tokens == 10
        if scenario == "overcharge":
            assert decision.backend == "local"
            assert decision.reason_code == ERROR_MODEL_PRICE_BOUND
            assert decision.receipt.reported_cost_usd == Decimal("0.01")
            assert accounted_cost(connection, version) == 10_000_000
            blocked = request_json(
                connection,
                claimed,
                settings,
                request.model_copy(update={"context_id": "next"}),
                ModelUnavailable,
                bytes(range(32)),
                environment={"LLM_API_KEY": "test-key"},
                transport=transport,
            )
            assert blocked.reason_code == ERROR_MODEL_PRICE_BOUND
            assert calls == 1
        else:
            assert decision.backend == "remote"
            assert decision.receipt.reported_cost_usd == 0
            assert accounted_cost(connection, version) == (
                10_000 if scenario == "judge" else 6_500
            )
