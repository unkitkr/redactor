"""Evaluation integration: fixed annotations and actual rewriting/verification."""

import json
from pathlib import Path

from redactor.evaluation.metrics import reference_spans, span_counts
from redactor.evaluation.text import evaluate_text_examples
from redactor.inference.ner import load_local_ner
from redactor.schemas.configuration import LocalSettings
from redactor.schemas.evaluation import EvaluationSpan, TextExample
from redactor.utils.constants import EVALUATION_TEXT_CORPUS


def test_fixed_corpus_and_real_adapter_report_every_case() -> None:
    examples = tuple(
        TextExample.model_validate(item)
        for item in json.loads(Path(EVALUATION_TEXT_CORPUS).read_text())
    )
    assert len(examples) == len({item.case_id for item in examples}) == 40
    for example in examples:
        spans = sorted(reference_spans(example), key=lambda span: span.start)
        assert all(
            left.end <= right.start
            for left, right in zip(spans, spans[1:], strict=False)
        )
        assert all(value in example.text for value in example.clinical)
    adapter = load_local_ner(LocalSettings())
    for combined in (False, True):
        report = evaluate_text_examples(examples, adapter, combined=combined)
        assert report["case_count"] == 40
        assert len(report["cases"]) == 40  # type: ignore[arg-type]
        assert "Elena Marlow" not in json.dumps(report)


def test_exact_metrics_do_not_credit_partial_or_wrong_type_spans() -> None:
    expected = (EvaluationSpan(start=1, end=12, kind="person"),)
    for predicted in (
        (EvaluationSpan(start=1, end=7, kind="person"),),
        (EvaluationSpan(start=1, end=12, kind="organization"),),
    ):
        counts = span_counts(expected, predicted)
        assert (counts.true_positive, counts.false_positive, counts.false_negative) == (
            0,
            1,
            1,
        )
    assert span_counts(expected, expected).f1 == 1


def test_ocr_metrics_distinguish_reading_from_safe_localization(tmp_path: Path) -> None:
    from redactor.evaluation.ocr import evaluate_ocr
    from redactor.schemas.evaluation import OcrExample, OcrReference, OcrRegion

    example = OcrExample(
        case_id="geometry",
        image=str(tmp_path / "image.png"),
        reference_text="MRN 12345 Metformin 500 mg",
        regions=(
            OcrReference(text="MRN 12345", box=(10, 10, 80, 30)),
            OcrReference(
                text="Metformin 500 mg", box=(10, 50, 150, 70), sensitive=False
            ),
        ),
    )

    def accurate_ocr(_: Path) -> tuple[OcrRegion, ...]:
        return tuple(
            OcrRegion(text=item.text, box=item.box) for item in example.regions
        )

    report = evaluate_ocr((example,), accurate_ocr)
    assert report["character_error_rate"] == 0
    totals = report["totals"]
    assert isinstance(totals, dict)
    assert totals["identifiers_localized"] == 1
    assert totals["identifier_boxes_overlapping_clinical"] == 0

    def broad_ocr(_: Path) -> tuple[OcrRegion, ...]:
        return (OcrRegion(text=example.reference_text, box=(0, 0, 200, 100)),)

    broad = evaluate_ocr((example,), broad_ocr)["totals"]
    assert isinstance(broad, dict)
    assert broad["identifiers_recovered"] == 1
    assert broad["identifier_boxes_overlapping_clinical"] == 1


def test_remote_evaluation_replays_from_private_ledger_without_credentials(
    tmp_path: Path,
) -> None:
    import hashlib

    import httpx
    import pytest

    from redactor.agents.detector.prompts import detection_request
    from redactor.evaluation.remote import load_remote_ner, remote_settings
    from redactor.evaluation.state import evaluation_state
    from redactor.schemas.entities import TextEntities
    from redactor.utils.constants import EVALUATION_REMOTE_MODELS
    from redactor.utils.errors import ERROR_RUN_ACTIVE
    from redactor.utils.provider import request_json

    source = tmp_path / "synthetic.txt"
    source.write_text("No personal identifiers in this synthetic example.")
    state = tmp_path / "state"
    model = EVALUATION_REMOTE_MODELS[0]
    calls = 0

    async def endpoint(_: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(
            200,
            json={
                "id": "evaluation-test",
                "object": "chat.completion",
                "created": 0,
                "model": model,
                "choices": [
                    {
                        "index": 0,
                        "finish_reason": "stop",
                        "message": {"role": "assistant", "content": '{"entities":[]}'},
                    }
                ],
                "usage": {
                    "prompt_tokens": 20,
                    "completion_tokens": 10,
                    "total_tokens": 30,
                },
            },
        )

    text = source.read_text()
    with evaluation_state(state, source, "analyze") as (connection, claimed, key):
        with (
            pytest.raises(RuntimeError, match=ERROR_RUN_ACTIVE),
            evaluation_state(state, source, "analyze"),
        ):
            pass
        result = request_json(
            connection,
            claimed,
            remote_settings(model),
            detection_request(text, hashlib.sha256(text.encode()).hexdigest()),
            TextEntities,
            key,
            environment={"LLM_API_KEY": "test-only"},
            transport=httpx.MockTransport(endpoint),
        )
        assert result.backend == "remote"
    with evaluation_state(state, source, "analyze") as (connection, claimed, key):
        adapter = load_remote_ner(
            connection, claimed, model, key, "", state / "receipts.jsonl"
        )
        assert adapter(text) == ()
    assert calls == 1
    assert not (state / "receipts.jsonl").exists()
    assert (state / "encryption.key").stat().st_mode & 0o777 == 0o600
