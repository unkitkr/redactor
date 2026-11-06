"""Run hosted detection through actual queue steps, replay and independent checks."""

import csv
import json
import sqlite3
from decimal import Decimal
from pathlib import Path

import httpx
import pytest

from redactor.agents.detector import adapter as detector_adapter
from redactor.coordinator.bootstrap import prepare_run
from redactor.coordinator.reconcile import reconcile_run
from redactor.inference.model_loader import load_local_ner
from redactor.persistence.files.registration import prepare_task
from redactor.persistence.models.observations import (
    read_detection_observation,
    save_detection_observation,
)
from redactor.persistence.queue.tasks import (
    claim_task,
    enqueue_task,
    recover_interrupted,
)
from redactor.schemas.configuration import PipelineSettings, RemoteSettings
from redactor.schemas.entities import EntityDetection, TextEntities, TextEntity
from redactor.schemas.persistence import Task
from redactor.utils.errors import ERROR_STALE_ATTEMPT
from redactor.workers.handlers import pipeline_handlers
from redactor.workers.pipeline import execute_task


@pytest.mark.parametrize(
    "scenario", ("hosted", "revoked", "rate_limited", "garbage", "omitted", "disabled")
)
def test_hosted_pipeline_replays_falls_back_and_verifies_independently(
    connection: sqlite3.Connection,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    scenario: str,
) -> None:
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    source = tmp_path / "input"
    source.mkdir()
    original = source / "records.csv"
    narrative = "Jane Smith returned for review."
    if scenario == "omitted":
        # Known patient mentions now have deterministic coverage. Keep testing
        # an omitted, unlinked person that only the independent local pass finds.
        narrative += " Dana Mitchell reviewed the chart."
    original.write_text(
        "patient,mrn,birth_date,admit_ts,dx_codes,comments\n"
        "Jane Smith,001234,1970-01-02,2026-01-02,E11.9,"
        f"{narrative}\n"
    )
    settings = PipelineSettings(
        remote=RemoteSettings(
            enabled=scenario != "disabled",
            base_url="https://model.example/v1",
            model="test-model",
            input_usd_per_million=Decimal("1"),
            output_usd_per_million=Decimal("1"),
            max_attempts=2,
            retry_initial_seconds=0.001,
            retry_max_seconds=0.002,
        )
    )
    calls = 0

    async def endpoint(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        assert not connection.in_transaction
        if scenario == "disabled":
            pytest.fail("The global disable switch must prevent all HTTP calls")
        if scenario == "revoked":
            return httpx.Response(401)
        if scenario == "rate_limited":
            return httpx.Response(429, headers={"retry-after": "0"})
        text = json.loads(json.loads(request.content)["messages"][1]["content"])["text"]
        entities: tuple[TextEntity, ...] = ()
        if "Jane Smith" in text and scenario != "omitted":
            start = text.index("Jane Smith")
            entities = (
                TextEntity(
                    start=start,
                    end=start + len("Jane Smith"),
                    text="Jane Smith",
                    entity_type="person",
                ),
            )
        content = (
            "not JSON"
            if scenario == "garbage"
            else TextEntities(entities=entities).model_dump_json()
        )
        return httpx.Response(
            200,
            json={
                "id": "pipeline-test",
                "object": "chat.completion",
                "created": 0,
                "model": "test-model",
                "choices": [
                    {
                        "index": 0,
                        "finish_reason": "stop",
                        "message": {"role": "assistant", "content": content},
                    }
                ],
                "usage": {
                    "prompt_tokens": 20,
                    "completion_tokens": 20,
                    "total_tokens": 40,
                },
            },
        )

    key = bytes(range(32))
    local_ner = load_local_ner(settings.local)
    run = prepare_run(connection, source, settings, key)
    handlers = pipeline_handlers(
        settings,
        key,
        local_ner,
        run.resolution_task_id,
        model_transport=httpx.MockTransport(endpoint),
    )
    inspected = claim_task(connection, step="inspect")
    assert inspected is not None
    execute_task(connection, inspected, handlers)
    analysis = claim_task(connection, step="analyze")
    assert analysis is not None
    # Simulate interruption after durable observations but before accepting the step.
    handlers["analyze"](connection, analysis)
    analyzed_calls = calls
    recover_interrupted(connection)
    retry = claim_task(connection, step="analyze")
    assert retry is not None
    with pytest.raises(ValueError, match=f"^{ERROR_STALE_ATTEMPT}$"):
        save_detection_observation(
            connection,
            analysis,
            "comments",
            EntityDetection(entities=(), backend="local"),
            key,
        )
    execute_task(connection, retry, handlers)
    assert calls == analyzed_calls

    disabled = settings.model_copy(
        update={"remote": settings.remote.model_copy(update={"enabled": False})}
    )
    handlers = pipeline_handlers(disabled, key, local_ner, run.resolution_task_id)
    while task := claim_task(connection):
        execute_task(connection, task, handlers)
    report = reconcile_run(connection, run, key)
    assert report.complete and report.inventoried == 1
    assert calls == analyzed_calls
    if scenario == "omitted":
        # The detector claimed no name existed. The independent verifier rejects it.
        assert report.published == 0 and report.quarantined == 1
        assert report.files[0].reason == "residual_phi_detected"
    else:
        assert report.published == 1 and report.quarantined == 0, report
        with (tmp_path / "output/published/records.csv").open(newline="") as stream:
            row = next(csv.DictReader(stream))
        assert row["patient"] != "Jane Smith"
        assert row["patient"] in row["comments"]
        assert row["dx_codes"] == "E11.9"
        assert row["comments"].endswith(" returned for review.")
    if scenario == "disabled":
        assert calls == 0 and report.files[0].cost_bound_nanos == 0
    else:
        assert calls > 0
    if scenario == "revoked":
        assert calls == 1  # Authentication failure disables subsequent requests.
    if scenario == "rate_limited":
        assert calls <= 4  # At most two attempts for each of the two unique texts.
    assert "Jane Smith" not in report.model_dump_json()
    payloads = connection.execute(
        "SELECT encrypted_payload FROM detection_observations"
    ).fetchall()
    assert payloads and all(b"Jane Smith" not in row[0] for row in payloads)


def test_saved_remote_answer_survives_interruption_before_observation(
    connection: sqlite3.Connection,
    source_file: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    settings = PipelineSettings(
        remote=RemoteSettings(
            enabled=True,
            base_url="https://model.example/v1",
            model="test-model",
            input_usd_per_million=Decimal("1"),
            output_usd_per_million=Decimal("1"),
        )
    )
    text = "Jane Smith returned for review."
    expected = (TextEntity(start=0, end=10, text="Jane Smith", entity_type="person"),)
    calls = 0

    async def endpoint(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        assert calls == 1
        assert not connection.in_transaction
        requested = json.loads(json.loads(request.content)["messages"][1]["content"])
        assert requested["text"] == text
        return httpx.Response(
            200,
            json={
                "id": "interrupted-analysis",
                "object": "chat.completion",
                "created": 0,
                "model": "test-model",
                "choices": [
                    {
                        "index": 0,
                        "finish_reason": "stop",
                        "message": {
                            "role": "assistant",
                            "content": TextEntities(
                                entities=expected
                            ).model_dump_json(),
                        },
                    }
                ],
                "usage": {
                    "prompt_tokens": 20,
                    "completion_tokens": 20,
                    "total_tokens": 40,
                },
            },
        )

    def unexpected_local_detection(value: str) -> tuple[TextEntity, ...]:
        pytest.fail("A durable remote answer must replay without local inference")

    def interrupt_before_observation(
        database: sqlite3.Connection,
        claimed: Task,
        value: str,
        detection: EntityDetection,
        mapping_key: bytes,
    ) -> EntityDetection:
        assert not database.in_transaction
        assert detection.backend == "remote" and detection.entities == expected
        raise KeyboardInterrupt

    key = bytes(range(32))
    enqueue_task(connection, prepare_task(source_file, "analyze", "interrupted-run"))
    analysis = claim_task(connection, step="analyze")
    assert analysis is not None
    recognize = detector_adapter.detection_adapter(
        connection,
        analysis,
        settings=settings,
        mapping_key=key,
        local_ner=unexpected_local_detection,
        transport=httpx.MockTransport(endpoint),
    )
    with monkeypatch.context() as interruption:
        interruption.setattr(
            detector_adapter, "save_detection_observation", interrupt_before_observation
        )
        with pytest.raises(KeyboardInterrupt):
            recognize(text)

    assert calls == 1
    assert connection.execute("SELECT COUNT(*) FROM model_decisions").fetchone()[0] == 1
    assert read_detection_observation(connection, analysis.task_id, text, key) is None
    recover_interrupted(connection)
    retry = claim_task(connection, step="analyze")
    assert retry is not None and retry.attempt_count == 2
    monkeypatch.delenv("LLM_API_KEY")
    disabled = settings.model_copy(
        update={"remote": settings.remote.model_copy(update={"enabled": False})}
    )
    resumed = detector_adapter.detection_adapter(
        connection,
        retry,
        settings=disabled,
        mapping_key=key,
        local_ner=unexpected_local_detection,
        transport=httpx.MockTransport(endpoint),
    )
    assert resumed(text) == expected
    assert calls == 1
    saved = read_detection_observation(connection, retry.task_id, text, key)
    assert saved is not None and saved.backend == "remote"
    assert saved.entities == expected
