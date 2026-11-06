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
from redactor.utils.errors import ERROR_MODEL_PRICE_BOUND, ERROR_MODEL_RESPONSE
from redactor.utils.provider import request_json


def test_openrouter_routing_receipts_and_overcharge_fail_closed(
    connection: sqlite3.Connection, source_file: Path
) -> None:
    for scenario in ("detector", "judge", "overcharge", "invalid_cost"):
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
            reported_cost = (
                "NaN" if case == "invalid_cost" else 0.01 if case == "overcharge" else 0
            )
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
                        "prompt_tokens": 10,
                        "completion_tokens": 10,
                        "total_tokens": 20,
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
        if scenario == "invalid_cost":
            assert decision.reason_code == ERROR_MODEL_RESPONSE
            assert decision.receipt is None
            assert accounted_cost(connection, version) > 0
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
