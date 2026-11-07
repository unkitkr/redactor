"""Hosted judge integration through SQLite, the SDK boundary and fake transports."""

import asyncio
import base64
import io
import json
import sqlite3
from decimal import Decimal
from pathlib import Path

import httpx
from PIL import Image

from redactor.agents.judge.evidence import build_judge_evidence
from redactor.agents.judge.findings import apply_judge_findings
from redactor.agents.judge.judge import judge_saved_evidence
from redactor.persistence.files.registration import register_file
from redactor.persistence.models.budget import accounted_cost
from redactor.persistence.queue.tasks import claim_task, recover_interrupted
from redactor.schemas.configuration import (
    PipelineSettings,
    RemoteSettings,
    VerificationSettings,
)
from redactor.schemas.judge import (
    JudgeAssessment,
    JudgeEvidence,
    JudgeFinding,
    JudgeOutcome,
)
from redactor.schemas.persistence import Artifact, Task
from redactor.schemas.redaction import TextRange
from redactor.schemas.verification import (
    ResidualCheck,
    VerificationCheck,
    VerificationContext,
)
from redactor.utils.constants import (
    CHECK_CLINICAL,
    CHECK_COVERAGE,
    CHECK_PIXELS,
    CHECK_RESIDUAL_PHI,
    CHECK_STRUCTURE,
    CHECK_TRANSFORMATIONS,
    JUDGE_FAILING_VERDICTS,
    JUDGE_PROMPT_VERSION,
    JUDGE_VERDICT_CLEAN,
    VERIFICATION_FAIL,
    VERIFICATION_PASS,
    VERIFICATION_UNKNOWN,
)
from redactor.utils.errors import (
    ERROR_JUDGE_EVIDENCE,
    ERROR_MODEL_AUTH,
    ERROR_MODEL_BUDGET,
    ERROR_MODEL_CONFIGURATION,
    ERROR_MODEL_DISABLED,
    ERROR_MODEL_RESPONSE,
    ERROR_MODEL_TRANSIENT,
    ERROR_RESIDUAL_PHI,
    JUDGE_DEGRADATION_CODES,
)
from redactor.verification.verdict import conclude_verification

JUDGE_MODEL = "test-judge"
KEY = bytes(range(32))
BASE_REMOTE = RemoteSettings(
    enabled=True,
    base_url="https://model.example/v1",
    model="test-detector",
    input_usd_per_million=Decimal("1"),
    output_usd_per_million=Decimal("1"),
)


def _remote(**updates: bool | int | float | Decimal | str) -> RemoteSettings:
    return BASE_REMOTE.model_copy(update=updates)


def _settings(
    remote: RemoteSettings | None = None,
    verification: VerificationSettings | None = None,
) -> PipelineSettings:
    return PipelineSettings(
        remote=remote or BASE_REMOTE,
        verification=verification or _verification(judge_vision=False),
    )


def _verification(
    judge_vision: bool, *, judge_enabled: bool = True
) -> VerificationSettings:
    return VerificationSettings(
        judge_enabled=judge_enabled,
        judge_model=JUDGE_MODEL,
        judge_vision=judge_vision,
        input_usd_per_million=Decimal("1"),
        output_usd_per_million=Decimal("1"),
    )


def _residual(text: str, allowed: tuple[TextRange, ...] = ()) -> ResidualCheck:
    return ResidualCheck(
        text=text, statistical_text=text, exemptions=(), allowed=allowed
    )


def _png(size: tuple[int, int]) -> bytes:
    stream = io.BytesIO()
    Image.new("RGB", size, "white").save(stream, format="PNG")
    return stream.getvalue()


def _checks(
    *, failed: bool = False, unknown: bool = False
) -> tuple[VerificationCheck, ...]:
    coverage = VerificationCheck(
        kind=CHECK_COVERAGE,
        status=(
            VERIFICATION_FAIL
            if failed
            else VERIFICATION_UNKNOWN
            if unknown
            else VERIFICATION_PASS
        ),
        expected=2,
        checked=1 if (failed or unknown) else 2,
        unassessed=1 if unknown else 0,
    )
    residual = VerificationCheck(
        kind=CHECK_RESIDUAL_PHI,
        status=VERIFICATION_FAIL if failed else VERIFICATION_PASS,
        expected=1,
        checked=1,
        failed=1 if failed else 0,
    )
    others = tuple(
        VerificationCheck(kind=kind, status=VERIFICATION_PASS, expected=1, checked=1)
        for kind in (
            CHECK_STRUCTURE,
            CHECK_TRANSFORMATIONS,
            CHECK_CLINICAL,
            CHECK_PIXELS,
        )
    )
    return (coverage, residual, *others)


def _verdict(checks: tuple[VerificationCheck, ...]) -> str:
    context = VerificationContext(
        original_sha256="a" * 64,
        identity_sha256="b" * 64,
        policy_sha256="c" * 64,
        has_pixels=True,
    )
    artifact = Artifact(path=Path("saved.dat"), sha256="d" * 64, size=1)
    return conclude_verification(context, "producer", artifact, checks).status


def _completion(content: str) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "id": "judge-test",
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


def _finding_response(finding: JudgeFinding) -> httpx.Response:
    return _completion(JudgeAssessment(findings=(finding,)).model_dump_json())


def _claim(connection: sqlite3.Connection, source_file: Path, version: str) -> Task:
    register_file(connection, source_file, "verify", version)
    claimed = claim_task(connection, processing_version=version)
    assert claimed is not None
    return claimed


def test_judge_flags_planted_findings_and_unsure_fails_closed(
    connection: sqlite3.Connection, source_file: Path
) -> None:
    text = "Follow up with Dr. Alice Smith within two weeks."
    allowed = (TextRange(start=17, end=37),)
    evidence = build_judge_evidence((_residual(text, allowed),))
    assert evidence.items[0].reference == "text:0"
    assert evidence.items[0].verified_spans == allowed
    assert evidence.omitted_items == 0
    for verdict in JUDGE_FAILING_VERDICTS:
        claimed = _claim(connection, source_file, f"judge-{verdict}-v1")
        calls = 0

        async def endpoint(
            request: httpx.Request, case: str = verdict
        ) -> httpx.Response:
            nonlocal calls
            calls += 1
            payload = json.loads(request.content)
            assert payload["model"] == JUDGE_MODEL
            system = payload["messages"][0]["content"]
            user = json.loads(payload["messages"][1]["content"])
            assert text not in system
            assert user["items"] == [
                {
                    "reference": "text:0",
                    "text": text,
                    "verified_spans": [{"start": 17, "end": 37}],
                }
            ]
            return _finding_response(
                JudgeFinding(reference="text:0", verdict=case, entity_kind="person")
            )

        outcome = judge_saved_evidence(
            connection,
            claimed,
            evidence,
            f"judge:{claimed.input_sha256}",
            settings=_settings(),
            mapping_key=KEY,
            environment={"LLM_API_KEY": "test-key"},
            transport=httpx.MockTransport(endpoint),
        )
        assert calls == 1
        assert outcome.reason_code is None
        assert outcome.findings == (
            JudgeFinding(reference="text:0", verdict=verdict, entity_kind="person"),
        )
        assert outcome.prompt_version == JUDGE_PROMPT_VERSION
        assert outcome.receipt is not None
        assert outcome.receipt.returned_model == JUDGE_MODEL
        application = apply_judge_findings(_checks(), outcome)
        assert application.degradation is None
        residual = next(
            check for check in application.checks if check.kind == CHECK_RESIDUAL_PHI
        )
        assert residual.status == VERIFICATION_FAIL
        assert residual.failed == 1
        assert residual.reason_code == ERROR_RESIDUAL_PHI
        assert _verdict(application.checks) == VERIFICATION_FAIL
        # A finding also creates the residual check when no local one exists.
        created = apply_judge_findings(_checks()[:1], outcome)
        appended = next(
            check for check in created.checks if check.kind == CHECK_RESIDUAL_PHI
        )
        assert appended.status == VERIFICATION_FAIL
        assert appended.failed == 1
        assert appended.reason_code == ERROR_RESIDUAL_PHI


def test_clean_judge_findings_leave_a_passing_local_verdict_unchanged(
    connection: sqlite3.Connection, source_file: Path
) -> None:
    claimed = _claim(connection, source_file, "judge-clean-v1")
    evidence = build_judge_evidence((_residual("Return if symptoms worsen."),))

    async def endpoint(request: httpx.Request) -> httpx.Response:
        return _finding_response(
            JudgeFinding(
                reference="text:0", verdict=JUDGE_VERDICT_CLEAN, entity_kind="person"
            )
        )

    outcome = judge_saved_evidence(
        connection,
        claimed,
        evidence,
        f"judge:{claimed.input_sha256}",
        settings=_settings(),
        mapping_key=KEY,
        environment={"LLM_API_KEY": "test-key"},
        transport=httpx.MockTransport(endpoint),
    )
    assert outcome.reason_code is None
    assert outcome.findings[0].verdict == JUDGE_VERDICT_CLEAN
    local = _checks()
    application = apply_judge_findings(local, outcome)
    assert application.checks == local
    assert application.degradation is None
    assert _verdict(application.checks) == VERIFICATION_PASS


def test_judge_degrades_to_the_local_verdict_and_records_the_reason(
    connection: sqlite3.Connection, source_file: Path
) -> None:
    evidence = build_judge_evidence((_residual("Return if symptoms worsen."),))
    cases: tuple[tuple[str, str, int, PipelineSettings], ...] = (
        (
            "unavailable",
            ERROR_MODEL_TRANSIENT,
            3,
            _settings(_remote(retry_initial_seconds=0.01, retry_max_seconds=0.02)),
        ),
        ("garbage", ERROR_MODEL_RESPONSE, 1, _settings()),
        (
            "timeout",
            ERROR_MODEL_TRANSIENT,
            1,
            _settings(
                _remote(timeout_seconds=0.05, deadline_seconds=5, max_attempts=1)
            ),
        ),
        ("disabled", ERROR_MODEL_DISABLED, 0, _settings(_remote(enabled=False))),
        (
            "switch_off",
            ERROR_MODEL_DISABLED,
            0,
            _settings(verification=_verification(False, judge_enabled=False)),
        ),
        (
            "unconfigured",
            ERROR_MODEL_CONFIGURATION,
            0,
            _settings(
                verification=VerificationSettings(
                    input_usd_per_million=Decimal("1"),
                    output_usd_per_million=Decimal("1"),
                )
            ),
        ),
        (
            "budget",
            ERROR_MODEL_BUDGET,
            0,
            _settings(_remote(budget_usd=Decimal("0.000001"))),
        ),
        ("unknown_reference", ERROR_JUDGE_EVIDENCE, 1, _settings()),
    )
    for scenario, reason, expected_calls, settings in cases:
        claimed = _claim(connection, source_file, f"judge-degrade-{scenario}")
        calls = 0

        async def endpoint(
            request: httpx.Request, case: str = scenario
        ) -> httpx.Response:
            nonlocal calls
            calls += 1
            assert json.loads(request.content)["model"] == JUDGE_MODEL
            if case == "unavailable":
                return httpx.Response(500)
            if case == "garbage":
                return httpx.Response(200, content=b"not JSON")
            if case == "timeout":
                await asyncio.sleep(1)
            if case == "unknown_reference":
                return _finding_response(
                    JudgeFinding(
                        reference="text:9", verdict="leak", entity_kind="person"
                    )
                )
            return _completion(JudgeAssessment().model_dump_json())

        outcome = judge_saved_evidence(
            connection,
            claimed,
            evidence,
            f"judge:{claimed.input_sha256}",
            settings=settings,
            mapping_key=KEY,
            environment={"LLM_API_KEY": "test-key"},
            transport=httpx.MockTransport(endpoint),
        )
        assert calls == expected_calls, scenario
        assert outcome.findings == (), scenario
        assert outcome.reason_code == reason, scenario
        assert outcome.reason_code in JUDGE_DEGRADATION_CODES, scenario
        local = _checks()
        application = apply_judge_findings(local, outcome)
        assert application.checks == local, scenario
        assert application.degradation is not None, scenario
        assert application.degradation.reason_code == reason, scenario
        assert _verdict(application.checks) == VERIFICATION_PASS, scenario


def test_judge_cannot_clear_local_failures_or_unknown_coverage() -> None:
    clean = apply_judge_findings(
        _checks(failed=True), JudgeOutcome(prompt_version=JUDGE_PROMPT_VERSION)
    )
    assert clean.checks == _checks(failed=True)
    assert clean.degradation is None
    assert _verdict(clean.checks) == VERIFICATION_FAIL
    unknown = apply_judge_findings(
        _checks(unknown=True), JudgeOutcome(prompt_version=JUDGE_PROMPT_VERSION)
    )
    assert unknown.checks == _checks(unknown=True)
    assert _verdict(unknown.checks) == VERIFICATION_UNKNOWN
    leak = apply_judge_findings(
        _checks(failed=True),
        JudgeOutcome(
            findings=(
                JudgeFinding(reference="text:0", verdict="leak", entity_kind="person"),
            ),
            prompt_version=JUDGE_PROMPT_VERSION,
        ),
    )
    residual = next(check for check in leak.checks if check.kind == CHECK_RESIDUAL_PHI)
    assert residual.failed == 2
    assert residual.reason_code == ERROR_RESIDUAL_PHI
    assert _verdict(leak.checks) == VERIFICATION_FAIL


def test_judge_replays_identical_findings_without_a_second_call_or_charge(
    connection: sqlite3.Connection, source_file: Path
) -> None:
    claimed = _claim(connection, source_file, "judge-replay-v1")
    evidence = build_judge_evidence(
        (_residual("The patient met with their daughter Margaret at home."),)
    )
    calls = 0

    async def endpoint(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return _finding_response(
            JudgeFinding(reference="text:0", verdict="leak", entity_kind="person")
        )

    transport = httpx.MockTransport(endpoint)
    outcome = judge_saved_evidence(
        connection,
        claimed,
        evidence,
        f"judge:{claimed.input_sha256}",
        settings=_settings(),
        mapping_key=KEY,
        environment={"LLM_API_KEY": "test-key"},
        transport=transport,
    )
    assert outcome.findings[0].verdict == "leak"
    cost = accounted_cost(connection, claimed.processing_version)
    assert cost > 0
    recover_interrupted(connection)
    resumed = claim_task(connection, processing_version=claimed.processing_version)
    assert resumed is not None
    replay = judge_saved_evidence(
        connection,
        resumed,
        evidence,
        f"judge:{resumed.input_sha256}",
        settings=_settings(_remote(enabled=False)),
        mapping_key=KEY,
        environment={},
        transport=transport,
    )
    assert replay == outcome
    assert calls == 1
    assert accounted_cost(connection, claimed.processing_version) == cost


def test_vision_requests_are_built_only_when_enabled_and_image_evidence_exists(
    connection: sqlite3.Connection, source_file: Path
) -> None:
    text = "Wound photo archived with the visit record."
    content = _png((16, 16))
    frame: tuple[bytes, tuple[int, int], str] = (content, (16, 16), "image/png")
    scenarios: tuple[tuple[str, PipelineSettings, JudgeEvidence, bool], ...] = (
        (
            "vision",
            _settings(verification=_verification(True)),
            build_judge_evidence((_residual(text),), images=(frame,)),
            True,
        ),
        (
            "switched_off",
            _settings(verification=_verification(False)),
            build_judge_evidence((_residual(text),), images=(frame,)),
            False,
        ),
        (
            "no_images",
            _settings(verification=_verification(True)),
            build_judge_evidence((_residual(text),)),
            False,
        ),
        (
            "no_text",
            _settings(verification=_verification(False)),
            build_judge_evidence((), images=(frame,)),
            False,
        ),
    )
    for scenario, settings, evidence, expect_image in scenarios:
        claimed = _claim(connection, source_file, f"judge-vision-{scenario}")
        calls = 0

        async def endpoint(
            request: httpx.Request, case: str = scenario
        ) -> httpx.Response:
            nonlocal calls
            calls += 1
            payload = json.loads(request.content)
            assert payload["model"] == JUDGE_MODEL
            message = payload["messages"][1]["content"]
            if case == "vision":
                assert isinstance(message, list)
                text_part, image_part = message
                assert text_part["type"] == "text"
                summary = json.loads(text_part["text"])
                assert summary["items"][0]["text"] == text
                assert "images" not in summary
                assert image_part["type"] == "image_url"
                expected = "data:image/png;base64," + base64.b64encode(content).decode()
                assert image_part["image_url"]["url"] == expected
                return _finding_response(
                    JudgeFinding(
                        reference="image:0", verdict="leak", entity_kind="person"
                    )
                )
            assert isinstance(message, str)
            assert "images" not in json.loads(message)
            return _completion(JudgeAssessment().model_dump_json())

        outcome = judge_saved_evidence(
            connection,
            claimed,
            evidence,
            f"judge:{claimed.input_sha256}",
            settings=settings,
            mapping_key=KEY,
            environment={"LLM_API_KEY": "test-key"},
            transport=httpx.MockTransport(endpoint),
        )
        if scenario == "no_text":
            assert calls == 0
            assert outcome.findings == ()
            assert outcome.reason_code is None
            continue
        assert calls == 1
        if expect_image:
            assert outcome.findings[0].reference == "image:0"
            application = apply_judge_findings(_checks(), outcome)
            assert _verdict(application.checks) == VERIFICATION_FAIL
        else:
            assert outcome.findings == ()
            assert outcome.reason_code is None


def test_evidence_bounds_count_dropped_entries() -> None:
    long_item = _residual(" ".join(["word"] * 800))
    short_item = _residual("short unresolved text")
    evidence = build_judge_evidence((long_item, short_item))
    assert evidence.items[0].text == "short unresolved text"
    assert evidence.omitted_items == 1
    many = tuple(_residual(f"unresolved text {number}") for number in range(12))
    bounded = build_judge_evidence(many)
    assert len(bounded.items) == 8
    assert bounded.omitted_items == 4
    small: tuple[bytes, tuple[int, int], str] = (_png((2, 2)), (2, 2), "image/png")
    oversized: tuple[bytes, tuple[int, int], str] = (
        b"x" * (512 * 1024 + 1),
        (2, 2),
        "image/png",
    )
    with_images = build_judge_evidence((), images=(oversized, small))
    assert len(with_images.images) == 1
    assert with_images.omitted_images == 1


def test_authentication_failure_degrades_and_local_failures_still_quarantine(
    connection: sqlite3.Connection, source_file: Path
) -> None:
    claimed = _claim(connection, source_file, "judge-auth-v1")
    evidence = build_judge_evidence((_residual("Contact the care team."),))
    calls = 0

    async def endpoint(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(401, content=b"must not be logged")

    outcome = judge_saved_evidence(
        connection,
        claimed,
        evidence,
        f"judge:{claimed.input_sha256}",
        settings=_settings(),
        mapping_key=KEY,
        environment={"LLM_API_KEY": "test-key"},
        transport=httpx.MockTransport(endpoint),
    )
    assert calls == 1
    assert outcome.findings == ()
    assert outcome.reason_code == ERROR_MODEL_AUTH
    assert outcome.reason_code in JUDGE_DEGRADATION_CODES
    local = _checks(failed=True)
    application = apply_judge_findings(local, outcome)
    assert application.checks == local
    assert application.degradation is not None
    assert _verdict(application.checks) == VERIFICATION_FAIL
