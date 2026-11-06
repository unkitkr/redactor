"""Offline rescoring uses encrypted historical answers and never changes its ledger."""

import hashlib
import json
import sqlite3
from collections import Counter
from pathlib import Path

import httpx
import pytest

from redactor.agents.detector.prompts import detection_request
from redactor.evaluation.remote import remote_settings, with_local_fallback
from redactor.evaluation.replay import load_replay_ner, replay_state
from redactor.evaluation.state import evaluation_state
from redactor.schemas.entities import TextEntities, TextEntity
from redactor.utils.constants import (
    EVALUATION_REMOTE_MODELS,
    PIPELINE_VERSION,
)
from redactor.utils.provider import request_json


def test_offline_replay_has_no_transport_and_preserves_real_encrypted_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "synthetic.txt"
    text = "Reviewed by Ada Mercer."
    source.write_text(text)
    state = tmp_path / "state"
    model = EVALUATION_REMOTE_MODELS[0]
    name = "Ada Mercer"
    start = text.index(name)
    expected = TextEntity(
        start=start, end=start + len(name), text=name, entity_type="person"
    )
    calls = 0

    async def endpoint(_: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(
            200,
            json={
                "id": "offline-evaluation-test",
                "object": "chat.completion",
                "created": 0,
                "model": model,
                "choices": [
                    {
                        "index": 0,
                        "finish_reason": "stop",
                        "message": {
                            "role": "assistant",
                            "content": json.dumps(
                                {"entities": [expected.model_dump()]}
                            ),
                        },
                    }
                ],
                "usage": {
                    "prompt_tokens": 20,
                    "completion_tokens": 10,
                    "total_tokens": 30,
                },
            },
        )

    with evaluation_state(state, source, "analyze") as (connection, task, key):
        decision = request_json(
            connection,
            task,
            remote_settings(model),
            detection_request(text, hashlib.sha256(text.encode()).hexdigest()),
            TextEntities,
            key,
            environment={"LLM_API_KEY": "test-only"},
            transport=httpx.MockTransport(endpoint),
        )
        assert decision.backend == "remote"
        before = tuple(connection.iterdump())
        ciphertext = connection.execute(
            "SELECT encrypted_payload FROM model_decisions"
        ).fetchone()[0]
        assert name.encode() not in ciphertext

    async def reject_network(_self: object, _request: httpx.Request) -> httpx.Response:
        raise AssertionError("Offline replay must not construct a live HTTP request")

    monkeypatch.setattr(
        httpx.AsyncHTTPTransport, "handle_async_request", reject_network
    )
    monkeypatch.delenv("OPENROUTER_KEY", raising=False)
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    cache_counts: Counter[str] = Counter()
    failures: list[str] = []
    local_inputs: list[str] = []

    def record_event(event: str) -> None:
        cache_counts[event] += 1

    def local(value: str) -> tuple[TextEntity, ...]:
        local_inputs.append(value)
        return ()

    with replay_state(state, source, "analyze") as (connection, task, key):
        adapter = load_replay_ner(
            connection, task, model, key, PIPELINE_VERSION, record_event
        )
        assert adapter(text) == (expected,)
        fallback = with_local_fallback(adapter, local, failures.append)
        assert fallback("A new input without a saved answer.") == ()
        wrong_version = load_replay_ner(
            connection, task, model, key, "unrecorded-version", record_event
        )
        with pytest.raises(ValueError, match="evaluation_cache_miss"):
            wrong_version(text)
        with pytest.raises(sqlite3.OperationalError):
            connection.execute("UPDATE model_circuits SET failures = failures + 1")
        assert connection.total_changes == 0
        assert tuple(connection.iterdump()) == before

    assert calls == 1
    assert cache_counts == {
        "cache_hits": 1,
        "grounded_remote_responses": 1,
        "cache_misses": 2,
    }
    assert failures == ["evaluation_cache_miss"]
    assert local_inputs == ["A new input without a saved answer."]
    assert not (state / "receipts.jsonl").exists()
