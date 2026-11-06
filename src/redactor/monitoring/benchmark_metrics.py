"""Project numeric measurements into a small, explicit display contract."""

import math
import re
from typing import Literal

from redactor.schemas.benchmarks import BenchmarkCase, BenchmarkMetric
from redactor.utils.constants import (
    MONITOR_BENCHMARK_CASE_PATTERN,
    MONITOR_MAX_BENCHMARK_CASES,
)


def mapping(value: object) -> dict[str, object]:
    if not isinstance(value, dict) or any(not isinstance(key, str) for key in value):
        raise ValueError("Expected an object")
    return value


def number(value: object) -> int | float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    try:
        return value if math.isfinite(value) and value >= 0 else None
    except OverflowError:
        return None


def metric(
    label: str,
    value: object,
    unit: Literal["percent", "seconds", "mib", "count", "text"] = "count",
) -> BenchmarkMetric:
    measured = number(value)
    if measured is not None and unit == "mib":
        measured /= 1024 * 1024
    return BenchmarkMetric(label=label, value=measured, unit=unit)


def text_metric(label: str, value: str) -> BenchmarkMetric:
    """Callers supply fixed descriptions, never arbitrary benchmark payloads."""
    return BenchmarkMetric(label=label, value=value, unit="text")


def _accuracy_metric(label: str, value: object) -> BenchmarkMetric:
    measured = number(value)
    return metric(
        label, measured if measured is not None and measured <= 1 else None, "percent"
    )


def text_metrics(evaluation: dict[str, object]) -> tuple[BenchmarkMetric, ...]:
    counts = mapping(evaluation.get("exact_typed_span_counts"))
    totals = mapping(evaluation.get("totals"))
    result = [
        _accuracy_metric("Precision", counts.get("precision")),
        _accuracy_metric("Recall", counts.get("recall")),
        _accuracy_metric("F1", counts.get("f1")),
        metric("True positives", counts.get("true_positive")),
        metric("False positives", counts.get("false_positive")),
        metric("False negatives", counts.get("false_negative")),
        metric("Reference mentions", totals.get("reference_mentions")),
        metric("Fully covered mentions", totals.get("fully_covered_mentions")),
        metric("Clinical overlaps", totals.get("clinical_span_false_positives")),
        metric("Policy/model abstentions", totals.get("abstentions", 0)),
        metric("Evaluation time", evaluation.get("seconds"), "seconds"),
    ]
    if evaluation.get("mode") == "combined_text_policy":
        result.extend(
            (
                metric("Verifier checked", totals.get("verifier_checked_cases", 0)),
                metric("False accepts", totals.get("verifier_false_accepts", 0)),
                metric("False rejects", totals.get("verifier_false_rejects", 0)),
            )
        )
    return tuple(result)


def resource_metrics(report: dict[str, object]) -> tuple[BenchmarkMetric, ...]:
    return (
        metric("Peak cgroup memory", report.get("peak_cgroup_bytes"), "mib"),
        metric("Peak process RSS", report.get("peak_process_rss_bytes"), "mib"),
        metric("Model loading", report.get("model_load_seconds"), "seconds"),
    )


def replay_metrics(report: dict[str, object]) -> tuple[BenchmarkMetric, ...]:
    if report.get("offline_replay") is not True:
        return ()
    cache = mapping(report.get("cache_counts", {}))
    fallbacks = mapping(report.get("fallbacks", {}))
    fallback_values = [number(value) for value in fallbacks.values()]
    fallback_total = (
        sum(value for value in fallback_values if value is not None)
        if "fallbacks" in report and all(value is not None for value in fallback_values)
        else None
    )
    return (
        *(
            metric(label, cache.get(key, 0) if "cache_counts" in report else None)
            for key, label in (
                ("cache_hits", "Cache hits"),
                ("cache_misses", "Cache misses"),
                ("grounded_remote_responses", "Grounded remote responses"),
                ("cached_local_decisions", "Cached local decisions"),
            )
        ),
        metric("Local fallbacks", fallback_total),
        metric("New model requests", report.get("new_model_requests")),
        metric("New model charges (USD)", report.get("new_model_cost_usd"), "text"),
    )


def ocr_metrics(evaluation: dict[str, object]) -> tuple[BenchmarkMetric, ...]:
    totals = mapping(evaluation.get("totals"))
    return (
        metric(
            "Character error rate", evaluation.get("character_error_rate"), "percent"
        ),
        *_ocr_counts(totals),
    )


def _ocr_counts(values: dict[str, object]) -> tuple[BenchmarkMetric, ...]:
    return tuple(
        metric(label, values.get(key))
        for key, label in (
            ("identifier_count", "Identifier targets"),
            ("identifiers_recovered", "Identifiers read"),
            ("identifiers_localized", "Identifiers localized"),
            ("clinical_count", "Clinical targets"),
            ("clinical_recovered", "Clinical targets read"),
            (
                "identifier_boxes_overlapping_clinical",
                "Boxes overlapping clinical text",
            ),
            ("reference_characters", "Reference characters"),
            ("character_edits", "Character edits"),
        )
    )


def cases(evaluation: dict[str, object], *, ocr: bool) -> tuple[BenchmarkCase, ...]:
    entries = evaluation.get("cases", [])
    if not isinstance(entries, list) or len(entries) > MONITOR_MAX_BENCHMARK_CASES:
        raise ValueError("Invalid case list")
    result: list[BenchmarkCase] = []
    identifiers: set[str] = set()
    for entry in entries:
        item = mapping(entry)
        identifier = item.get("case_id")
        if (
            not isinstance(identifier, str)
            or re.fullmatch(MONITOR_BENCHMARK_CASE_PATTERN, identifier) is None
            or identifier in identifiers
        ):
            raise ValueError("Invalid case identifier")
        identifiers.add(identifier)
        if ocr:
            metrics = (
                *_ocr_counts(item),
                metric("Evaluation time", item.get("seconds"), "seconds"),
                text_metric(
                    "Result", "Rejected response" if item.get("error") else "Measured"
                ),
            )
        else:
            counts = mapping(item.get("counts"))
            verdict = item.get("verifier_passed")
            status = (
                "Accepted"
                if verdict is True
                else "Rejected"
                if verdict is False
                else "Not checked"
            )
            metrics = (
                _accuracy_metric("Precision", counts.get("precision")),
                _accuracy_metric("Recall", counts.get("recall")),
                _accuracy_metric("F1", counts.get("f1")),
                metric("Covered mentions", item.get("covered_mentions")),
                metric("Reference mentions", item.get("reference_mentions")),
                metric("Clinical overlaps", item.get("clinical_span_false_positives")),
                text_metric("Verifier", status),
                text_metric(
                    "Detection",
                    "Abstained" if item.get("abstention_reason") else "Measured",
                ),
            )
        result.append(BenchmarkCase(case_id=identifier, metrics=metrics))
    return tuple(result)


def throughput_metrics(report: dict[str, object]) -> tuple[BenchmarkMetric, ...]:
    return (
        metric("Rows", report.get("rows")),
        metric("Input size", report.get("input_bytes"), "mib"),
        metric("Elapsed time", report.get("wall_seconds"), "seconds"),
        metric("Rows per second", report.get("rows_per_second"), "text"),
        metric("Input throughput (MiB/s)", report.get("input_mib_per_second"), "text"),
        metric("Peak cgroup memory", report.get("peak_cgroup_memory_bytes"), "mib"),
        metric("Published files", report.get("published_files")),
        metric("Quarantined files", report.get("quarantined_files")),
    )
