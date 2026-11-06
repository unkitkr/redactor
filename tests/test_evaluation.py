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
