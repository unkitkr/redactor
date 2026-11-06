"""Keep accuracy, replay and resource experiments distinct."""

from redactor.monitoring.benchmark_diagnostics import diagnostic_reports
from redactor.monitoring.benchmark_metadata import (
    corpus_digest,
    filename_model,
    model_label,
    platform_label,
    text_context,
    verifier_version,
)
from redactor.monitoring.benchmark_metrics import (
    cases,
    mapping,
    metric,
    ocr_metrics,
    replay_metrics,
    resource_metrics,
    text_metrics,
    throughput_metrics,
)
from redactor.schemas.benchmarks import BenchmarkReport


def normalize_reports(source: str, payload: object) -> tuple[BenchmarkReport, ...]:
    """Only recognized report fields enter the public response."""
    diagnostics = diagnostic_reports(source, payload)
    if diagnostics is not None:
        return diagnostics
    report = mapping(payload)
    if "evaluations" in report:
        return _text_reports(source, report)
    if "evaluation" in report:
        return (_ocr_report(source, report),)
    if report.get("measurement") == "initial_csv_baseline":
        return (
            BenchmarkReport(
                id=source,
                source=source,
                kind="throughput",
                model="Offline CSV pipeline",
                mode="initial_csv_baseline",
                context="Historical constrained container baseline",
                platform="Linux container",
                scope="Small baseline; not the 2 GiB / 30 minute acceptance test.",
                metrics=throughput_metrics(report),
            ),
        )
    raise ValueError("Unsupported benchmark report")


def _text_reports(
    source: str, report: dict[str, object]
) -> tuple[BenchmarkReport, ...]:
    evaluations = report["evaluations"]
    if not isinstance(evaluations, list) or len(evaluations) > 2:
        raise ValueError("Invalid evaluation list")
    result = []
    seen: set[str] = set()
    for value in evaluations:
        evaluation = mapping(value)
        mode = evaluation.get("mode")
        if (
            mode not in ("raw_ner", "combined_text_policy")
            or not isinstance(mode, str)
            or mode in seen
        ):
            raise ValueError("Invalid evaluation mode")
        seen.add(mode)
        case_rows = cases(evaluation, ocr=False)
        result.append(
            BenchmarkReport(
                id=f"{source}:{mode}",
                source=source,
                kind="text",
                model=model_label(report.get("model")),
                mode=mode,
                context=text_context(report, mode),
                platform=platform_label(report),
                verifier_version=verifier_version(report),
                corpus_sha256=corpus_digest(report),
                case_count=len(case_rows),
                scope=(
                    "Synthetic development text units; not clinical validation, "
                    "native-file publication or an LLM judge."
                ),
                metrics=text_metrics(evaluation)
                + resource_metrics(report)
                + (replay_metrics(report) if mode == "combined_text_policy" else ()),
                cases=case_rows,
            )
        )
    return tuple(result)


def _ocr_report(source: str, report: dict[str, object]) -> BenchmarkReport:
    evaluation = mapping(report["evaluation"])
    case_rows = cases(evaluation, ocr=True)
    hosted = report.get("remote_models_enabled") is True
    return BenchmarkReport(
        id=source,
        source=source,
        kind="ocr",
        model=filename_model(source),
        mode="ocr",
        context="Historical live hosted OCR"
        if hosted
        else "Historical constrained local OCR",
        platform="Hosted client on macOS" if hosted else platform_label(report),
        corpus_sha256=corpus_digest(report),
        case_count=len(case_rows),
        scope=(
            "Correlated image variants from three documents; text and geometry "
            "only, not safe image publication."
        ),
        metrics=ocr_metrics(evaluation)
        + (
            metric(
                "Inference time",
                report.get("seconds" if hosted else "inference_seconds"),
                "seconds",
            ),
            metric(
                "Rejected responses",
                sum(
                    any(
                        value.label == "Result" and value.value == "Rejected response"
                        for value in item.metrics
                    )
                    for item in case_rows
                ),
            ),
        )
        + resource_metrics(report),
        cases=case_rows,
    )
