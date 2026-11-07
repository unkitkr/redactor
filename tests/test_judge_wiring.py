"""Judge wiring integration: leak findings quarantine, degradations never weaken."""

import csv
import sqlite3
from collections.abc import Callable
from decimal import Decimal
from pathlib import Path

import httpx
import pytest

from redactor.coordinator.bootstrap import prepare_run
from redactor.inference.model_loader import load_local_ner_adapters
from redactor.persistence.files.results import read_step_result
from redactor.persistence.queue.tasks import claim_task
from redactor.schemas.configuration import (
    PipelineSettings,
    RemoteSettings,
    VerificationSettings,
)
from redactor.schemas.entities import NerAdapter, NerBatchAdapter
from redactor.schemas.judge import JudgeAssessment, JudgeFinding
from redactor.schemas.verification import VerificationVerdict
from redactor.utils.constants import (
    CHECK_RESIDUAL_PHI,
    STEP_PUBLISH,
    STEP_QUARANTINE,
    STEP_VERIFY,
    VERIFICATION_BATCH_RECORDS,
)
from redactor.utils.errors import ERROR_RESIDUAL_PHI, JUDGE_DEGRADATION_CODES
from redactor.workers.handlers import pipeline_handlers
from redactor.workers.pipeline import execute_task

JUDGE_MODEL = "test-judge"
KEY = bytes(range(32))


def _hosted_settings() -> PipelineSettings:
    return PipelineSettings(
        remote=RemoteSettings(
            enabled=True,
            base_url="https://model.example/v1",
            model="test-detector",
            input_usd_per_million=Decimal("1"),
            output_usd_per_million=Decimal("1"),
            max_attempts=1,
            retry_initial_seconds=0.01,
            retry_max_seconds=0.01,
            timeout_seconds=1.0,
            deadline_seconds=3.0,
        ),
        verification=VerificationSettings(
            judge_enabled=True,
            judge_model=JUDGE_MODEL,
            judge_vision=False,
            input_usd_per_million=Decimal("1"),
            output_usd_per_million=Decimal("1"),
        ),
    )


def _completion(content: str) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "id": "judge-wiring-test",
            "object": "chat.completion",
            "created": 0,
            "model": JUDGE_MODEL,
            "choices": [
                {
                    "index": 0,
                    "finish_reason": "stop",
                    "message": {"role": "assistant", "content": content},
                }
            ],
            "usage": {"prompt_tokens": 10, "completion_tokens": 10, "total_tokens": 20},
        },
    )


def _leak_response(request: httpx.Request) -> httpx.Response:
    return _completion(
        JudgeAssessment(
            findings=(
                JudgeFinding(reference="text:0", verdict="leak", entity_kind="person"),
            )
        ).model_dump_json()
    )


def _unavailable_response(request: httpx.Request) -> httpx.Response:
    return httpx.Response(500, text="unavailable")


def _judge_transport(
    handler: Callable[[httpx.Request], httpx.Response],
) -> tuple[httpx.MockTransport, dict[str, int]]:
    """Analysis ran locally, so every request in the verify phase is the judge."""
    calls = {"judge": 0}

    async def endpoint(request: httpx.Request) -> httpx.Response:
        calls["judge"] += 1
        return handler(request)

    return httpx.MockTransport(endpoint), calls


def _prepare_through_rewrite(
    connection: sqlite3.Connection, tmp_path: Path, settings: PipelineSettings
) -> tuple[str, NerAdapter, NerBatchAdapter]:
    source = tmp_path / "input"
    source.mkdir()
    note = (
        "Glucose 106 mg/dL.\nTemperature 37 °C.\nCall 206-555-0101."
        "\nFollow-up discussed."
    )
    path = source / "records.csv"
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream, quoting=csv.QUOTE_ALL)
        writer.writerow(("patient", "mrn", "birth_date", "admit_ts", "comments"))
        for index in range(VERIFICATION_BATCH_RECORDS + 3):
            name = "Renée Marin" if index % 2 else "Rene\u0301e Marin"
            writer.writerow((name, "27193", "1974-02-08", "2026-04-05", note))
    single, batch = load_local_ner_adapters(settings.local)
    assert batch is not None
    run = prepare_run(connection, source, settings, KEY)
    handlers = pipeline_handlers(
        settings,
        KEY,
        single,
        run.resolution_task_id,
        verifier_ner=single,
        verification_batch=batch,
    )
    for step in ("inspect", "analyze", "resolve", "rewrite"):
        task = claim_task(connection, step=step)
        assert task is not None, step
        execute_task(connection, task, handlers)
    return run.resolution_task_id, single, batch


def _run_verification(
    connection: sqlite3.Connection,
    settings: PipelineSettings,
    resolution_task_id: str,
    single: NerAdapter,
    batch: NerBatchAdapter,
    transport: httpx.MockTransport | None,
) -> VerificationVerdict:
    handlers = pipeline_handlers(
        settings,
        KEY,
        single,
        resolution_task_id,
        verifier_ner=single,
        verification_batch=batch,
        model_transport=transport,
    )
    verification = claim_task(connection, step=STEP_VERIFY)
    assert verification is not None
    execute_task(connection, verification, handlers)
    verdict = read_step_result(connection, verification.task_id, VerificationVerdict)
    assert verdict is not None
    return verdict


def test_judge_leak_finding_quarantines_a_locally_passing_file(
    connection: sqlite3.Connection,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    resolution, single, batch = _prepare_through_rewrite(
        connection, tmp_path, PipelineSettings()
    )
    transport, calls = _judge_transport(_leak_response)
    verdict = _run_verification(
        connection, _hosted_settings(), resolution, single, batch, transport
    )
    assert calls["judge"] == 1
    assert verdict.status == "fail"
    assert verdict.judge_degradation is None
    residual = next(
        check for check in verdict.checks if check.kind == CHECK_RESIDUAL_PHI
    )
    assert residual.failed == 1
    assert residual.reason_code == ERROR_RESIDUAL_PHI
    successor = claim_task(connection, step=STEP_QUARANTINE)
    assert successor is not None


def test_judge_unavailability_degrades_to_the_local_verdict(
    connection: sqlite3.Connection,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    resolution, single, batch = _prepare_through_rewrite(
        connection, tmp_path, PipelineSettings()
    )
    transport, calls = _judge_transport(_unavailable_response)
    verdict = _run_verification(
        connection, _hosted_settings(), resolution, single, batch, transport
    )
    assert calls["judge"] >= 1
    assert verdict.status == "pass"
    assert verdict.judge_degradation is not None
    assert verdict.judge_degradation in JUDGE_DEGRADATION_CODES
    successor = claim_task(connection, step=STEP_PUBLISH)
    assert successor is not None


def test_local_mode_never_calls_the_judge(
    connection: sqlite3.Connection, tmp_path: Path
) -> None:
    resolution, single, batch = _prepare_through_rewrite(
        connection, tmp_path, PipelineSettings()
    )

    def forbidden(request: httpx.Request) -> httpx.Response:
        raise AssertionError("local mode must not call any model endpoint")

    transport, calls = _judge_transport(forbidden)
    verdict = _run_verification(
        connection, PipelineSettings(), resolution, single, batch, transport
    )
    assert calls["judge"] == 0
    assert verdict.status == "pass"
    assert verdict.judge_degradation is None
