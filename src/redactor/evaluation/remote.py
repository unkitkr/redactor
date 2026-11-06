"""Benchmark the real provider with a shared durable budget and safe receipts.

The HTTP handler forwards real requests. It only adds OpenRouter routing caps and
records response metadata; document content and credentials never enter receipts.
"""

import hashlib
import json
import os
import sqlite3
from collections.abc import Callable
from decimal import Decimal
from pathlib import Path
from time import perf_counter

import httpx

from redactor.agents.detector.prompts import detection_request
from redactor.evaluation.failures import evaluation_failure
from redactor.inference.evidence import validate_entity_evidence
from redactor.schemas.configuration import PipelineSettings, RemoteSettings
from redactor.schemas.entities import NerAdapter, TextEntities, TextEntity
from redactor.schemas.persistence import Task
from redactor.utils.constants import (
    EVALUATION_OPENROUTER_URL,
    EVALUATION_REMOTE_DEADLINE,
    EVALUATION_REMOTE_INPUT_PRICE,
    EVALUATION_REMOTE_OUTPUT_PRICE,
    EVALUATION_REMOTE_OUTPUT_TOKENS,
    EVALUATION_REMOTE_TIMEOUT,
    MODEL_KEY_ENVIRONMENT,
    MODEL_REMOTE,
    MODEL_RESPONSE_BYTES,
)
from redactor.utils.errors import ERROR_MODEL_RESPONSE
from redactor.utils.provider import request_json


def remote_settings(model: str) -> PipelineSettings:
    input_price, output_price = (
        ("0.4", "1.5")
        if model.startswith("z-ai/")
        else (EVALUATION_REMOTE_INPUT_PRICE, EVALUATION_REMOTE_OUTPUT_PRICE)
    )
    return PipelineSettings(
        remote=RemoteSettings(
            base_url=EVALUATION_OPENROUTER_URL,
            model=model,
            input_usd_per_million=Decimal(input_price),
            output_usd_per_million=Decimal(output_price),
            timeout_seconds=EVALUATION_REMOTE_TIMEOUT,
            deadline_seconds=EVALUATION_REMOTE_DEADLINE,
            max_output_tokens=EVALUATION_REMOTE_OUTPUT_TOKENS,
            max_attempts=2,
        )
    )


def load_remote_ner(
    connection: sqlite3.Connection,
    claimed: Task,
    model: str,
    mapping_key: bytes,
    api_key: str,
    receipt_path: Path,
) -> NerAdapter:
    settings = remote_settings(model)
    transport = recording_transport(receipt_path, settings.remote)

    def recognize(text: str) -> tuple[TextEntity, ...]:
        context = hashlib.sha256(text.encode()).hexdigest()
        decision = request_json(
            connection,
            claimed,
            settings,
            detection_request(text, context),
            TextEntities,
            mapping_key,
            environment={MODEL_KEY_ENVIRONMENT: api_key},
            transport=transport,
        )
        if decision.backend != MODEL_REMOTE:
            raise ValueError(decision.reason_code or ERROR_MODEL_RESPONSE)
        return validate_entity_evidence(
            text, TextEntities.model_validate(decision.payload)
        )

    return recognize


def recording_transport(
    receipt_path: Path, settings: RemoteSettings
) -> httpx.MockTransport:
    async def forward(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        payload["provider"] = {
            "max_price": {
                "prompt": float(settings.input_usd_per_million or 0),
                "completion": float(settings.output_usd_per_million or 0),
                "request": 0,
                "image": 0,
            },
            "require_parameters": True,
        }
        payload["reasoning"] = {"enabled": payload["model"].startswith("z-ai/")}
        payload["temperature"] = 0
        user_content = json.loads(payload["messages"][1]["content"])
        if "evaluation_image_base64" in user_content:
            payload["messages"][1]["content"] = [
                {
                    "type": "image_url",
                    "image_url": {
                        "url": "data:image/png;base64,"
                        + user_content["evaluation_image_base64"]
                    },
                }
            ]
        content = json.dumps(payload).encode()
        headers = dict(request.headers)
        headers["content-length"] = str(len(content))
        forwarded = httpx.Request(
            request.method, request.url, headers=headers, content=content
        )
        started = perf_counter()
        async with httpx.AsyncHTTPTransport(retries=0) as transport:
            response = await transport.handle_async_request(forwarded)
            try:
                body = bytearray()
                async for chunk in response.aiter_bytes():
                    if len(body) + len(chunk) > MODEL_RESPONSE_BYTES:
                        raise ValueError(ERROR_MODEL_RESPONSE)
                    body.extend(chunk)
            finally:
                await response.aclose()
        receipt: dict[str, object] = {
            "requested_model": payload["model"],
            "input_sha256": hashlib.sha256(request.content).hexdigest(),
            "status_code": response.status_code,
            "seconds": perf_counter() - started,
        }
        if response.is_success:
            data = json.loads(body)
            usage = data.get("usage") or {}
            receipt.update(
                {
                    "response_id": data.get("id"),
                    "returned_model": data.get("model"),
                    "provider": data.get("provider"),
                    "input_tokens": usage.get("prompt_tokens"),
                    "output_tokens": usage.get("completion_tokens"),
                    "billed_cost_usd": usage.get("cost"),
                    "finish_reasons": [
                        item.get("finish_reason") for item in data.get("choices", [])
                    ],
                }
            )
        append_receipt(receipt_path, receipt)
        return httpx.Response(
            response.status_code, headers=response.headers, content=bytes(body)
        )

    return httpx.MockTransport(forward)


def append_receipt(path: Path, receipt: dict[str, object]) -> None:
    with path.open("a") as output:
        output.write(json.dumps(receipt) + "\n")
        output.flush()
        os.fsync(output.fileno())


def with_local_fallback(
    remote: NerAdapter, local: NerAdapter, record_failure: Callable[[str], None]
) -> NerAdapter:
    def recognize(text: str) -> tuple[TextEntity, ...]:
        try:
            return remote(text)
        except ValueError as error:
            record_failure(evaluation_failure(error))
            return local(text)

    return recognize
