"""Run raw NER and the combined text policy against the same manual annotations."""

from collections import Counter
from time import perf_counter

from redactor.evaluation.failures import evaluation_failure
from redactor.evaluation.metrics import (
    clinical_overlaps,
    detection_counts,
    fully_covered,
    reference_spans,
    span_counts,
)
from redactor.inference.text import find_text_phi
from redactor.policy.text import apply_text_edits, text_edits
from redactor.schemas.entities import NerAdapter
from redactor.schemas.evaluation import EvaluationSpan, TextExample
from redactor.schemas.redaction import TextContext
from redactor.utils.constants import EVALUATION_FINDING_TYPES
from redactor.verification.text import verify_text_changes


def evaluate_text_examples(
    examples: tuple[TextExample, ...],
    adapter: NerAdapter,
    *,
    combined: bool,
    verifier_adapter: NerAdapter | None = None,
) -> dict[str, object]:
    totals: Counter[str] = Counter()
    per_kind: dict[str, Counter[str]] = {}
    cases: list[dict[str, object]] = []
    kind_mapping = dict(EVALUATION_FINDING_TYPES)
    started = perf_counter()
    for example in examples:
        expected = reference_spans(example)
        predicted: tuple[EvaluationSpan, ...] = ()
        error = None
        verifier_passed: bool | None = None
        try:
            if combined:
                findings = find_text_phi(
                    example.text,
                    adapter,
                    patient_name=example.patient_name,
                    provider_name=example.provider_name,
                )
                predicted = tuple(
                    EvaluationSpan(
                        start=item.start,
                        end=item.end,
                        kind=kind_mapping.get(item.kind, item.kind),
                    )
                    for item in findings
                )
                edits = text_edits(
                    findings,
                    TextContext(
                        context_key=example.case_id,
                        patient_name=example.patient_name,
                        provider_name=example.provider_name,
                        maximum_date_shift_days=365,
                    ),
                    bytes(range(32)),
                )
                output = apply_text_edits(example.text, edits)
                try:
                    verify_text_changes(
                        example.text,
                        output,
                        edits,
                        verifier_adapter or adapter,
                        free_text=True,
                        patient_name=example.patient_name,
                        provider_name=example.provider_name,
                    )
                except ValueError:
                    verifier_passed = False
                else:
                    verifier_passed = True
            else:
                predicted = tuple(
                    EvaluationSpan(
                        start=item.start, end=item.end, kind=item.entity_type
                    )
                    for item in adapter(example.text)
                )
        except Exception as exception:
            error = evaluation_failure(exception)
            totals["abstentions"] += 1
        counts = span_counts(expected, predicted)
        for field in ("true_positive", "false_positive", "false_negative"):
            totals[field] += getattr(counts, field)
        for kind in {span.kind for span in (*expected, *predicted)}:
            typed = span_counts(
                tuple(span for span in expected if span.kind == kind),
                tuple(span for span in predicted if span.kind == kind),
            )
            counter = per_kind.setdefault(kind, Counter())
            for field in ("true_positive", "false_positive", "false_negative"):
                counter[field] += getattr(typed, field)
        covered = sum(fully_covered(span, predicted) for span in expected)
        clinical_changes = clinical_overlaps(example, predicted)
        totals["reference_mentions"] += len(expected)
        totals["fully_covered_mentions"] += covered
        totals["clinical_span_false_positives"] += clinical_changes
        unsafe = covered != len(expected) or clinical_changes > 0
        if verifier_passed is not None:
            totals["verifier_checked_cases"] += 1
            totals["verifier_false_accepts"] += verifier_passed and unsafe
            totals["verifier_false_rejects"] += not verifier_passed and not unsafe
        cases.append(
            {
                "case_id": example.case_id,
                "counts": counts.model_dump(),
                "covered_mentions": covered,
                "reference_mentions": len(expected),
                "clinical_span_false_positives": clinical_changes,
                "abstention_reason": error,
                "verifier_passed": verifier_passed,
            }
        )
    return {
        "mode": "combined_text_policy" if combined else "raw_ner",
        "case_count": len(examples),
        "seconds": perf_counter() - started,
        "exact_typed_span_counts": detection_counts(
            totals["true_positive"], totals["false_positive"], totals["false_negative"]
        ).model_dump(),
        "totals": dict(totals),
        "per_kind": {
            kind: detection_counts(
                counts["true_positive"],
                counts["false_positive"],
                counts["false_negative"],
            ).model_dump()
            for kind, counts in sorted(per_kind.items())
        },
        "cases": cases,
    }
