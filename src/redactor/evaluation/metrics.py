"""Score exact typed spans and separately measure complete sensitive-span coverage."""

from collections.abc import Sequence

from redactor.schemas.evaluation import (
    DetectionCounts,
    EvaluationSpan,
    ReferenceMention,
    TextExample,
)
from redactor.utils.errors import ERROR_ENTITY_EVIDENCE


def reference_spans(example: TextExample) -> tuple[EvaluationSpan, ...]:
    return tuple(locate_mention(example.text, mention) for mention in example.mentions)


def locate_mention(text: str, mention: ReferenceMention) -> EvaluationSpan:
    start = -1
    for _ in range(mention.occurrence):
        start = text.find(mention.text, start + 1)
        if start < 0:
            raise ValueError(ERROR_ENTITY_EVIDENCE)
    return EvaluationSpan(start=start, end=start + len(mention.text), kind=mention.kind)


def span_counts(
    expected: Sequence[EvaluationSpan], predicted: Sequence[EvaluationSpan]
) -> DetectionCounts:
    truth = {(span.start, span.end, span.kind) for span in expected}
    actual = {(span.start, span.end, span.kind) for span in predicted}
    return detection_counts(
        len(truth & actual), len(actual - truth), len(truth - actual)
    )


def detection_counts(
    true_positive: int, false_positive: int, false_negative: int
) -> DetectionCounts:
    precision = (
        true_positive / (true_positive + false_positive)
        if true_positive + false_positive
        else None
    )
    recall = (
        true_positive / (true_positive + false_negative)
        if true_positive + false_negative
        else None
    )
    denominator = 2 * true_positive + false_positive + false_negative
    return DetectionCounts(
        true_positive=true_positive,
        false_positive=false_positive,
        false_negative=false_negative,
        precision=precision,
        recall=recall,
        f1=2 * true_positive / denominator if denominator else None,
    )


def fully_covered(
    expected: EvaluationSpan, predicted: Sequence[EvaluationSpan]
) -> bool:
    # Coverage is a privacy measure: a wrong category may still remove the value.
    return any(
        span.start <= expected.start and expected.end <= span.end for span in predicted
    )


def clinical_overlaps(example: TextExample, predicted: Sequence[EvaluationSpan]) -> int:
    overlaps = 0
    for text in example.clinical:
        span = locate_mention(
            example.text, ReferenceMention(text=text, kind="clinical")
        )
        overlaps += any(
            item.start < span.end and span.start < item.end for item in predicted
        )
    return overlaps
