"""Expose diagnostic evidence separately from accuracy rankings."""

from redactor.monitoring.benchmark_metadata import (
    filename_model,
    model_label,
    platform_label,
)
from redactor.monitoring.benchmark_metrics import mapping, metric, number, text_metric
from redactor.schemas.benchmarks import BenchmarkMetric, BenchmarkReport


def diagnostic_reports(
    source: str, payload: object
) -> tuple[BenchmarkReport, ...] | None:
    if source.endswith("gliner-parity.json"):
        return _parity_reports(source, payload)
    report = mapping(payload)
    if report.get("benchmark") == "dashboard_overhead":
        return (_overhead_report(source, report),)
    if source.endswith("glm-flash-rejected.json"):
        return (
            _diagnostic(
                source,
                "GLM 5.3 Flash",
                "rejected_configuration",
                (
                    text_metric("Status", "Requests rejected: reasoning was required"),
                    text_metric("Accuracy", "Not a model accuracy measurement"),
                ),
            ),
        )
    if source.endswith("nvidia-preflight.json"):
        return (
            _diagnostic(
                source,
                "nvidia/gliner-PII",
                "resource_preflight",
                (
                    metric("Published weight size", report.get("weight_bytes"), "mib"),
                    metric(
                        "Container memory limit",
                        report.get("memory_limit_bytes"),
                        "mib",
                    ),
                    text_metric(
                        "Status", "Excluded before loading; accuracy not measured"
                    ),
                ),
            ),
        )
    if source.endswith("openrouter-summary.json"):
        return (
            _diagnostic(
                source,
                "OpenRouter shared accounting",
                "cost_summary",
                (
                    metric(
                        "Reported billed cost (USD)",
                        report.get("reported_billed_usd"),
                        "text",
                    ),
                    metric(
                        "Conservative ledger (USD)",
                        report.get("conservative_ledger_usd"),
                        "text",
                    ),
                    text_metric(
                        "Accounting",
                        "Shared cumulative totals; do not sum report reservations",
                    ),
                ),
            ),
        )
    if source.endswith("-container.json"):
        return (
            _diagnostic(
                source,
                filename_model(source),
                "container_receipt",
                (
                    metric("vCPUs", report.get("cpus")),
                    metric("Memory limit", report.get("memory_bytes"), "mib"),
                    metric(
                        "Memory plus swap limit", report.get("memory_swap_bytes"), "mib"
                    ),
                    metric(
                        "Wall time including startup",
                        report.get("wall_seconds_including_container_start"),
                        "seconds",
                    ),
                    metric("Exit code", report.get("exit_code")),
                    text_metric(
                        "OOM",
                        "Yes"
                        if report.get("oom_killed") is True
                        else "No"
                        if report.get("oom_killed") is False
                        else "Not recorded",
                    ),
                ),
            ),
        )
    return None


def _diagnostic(
    source: str,
    model: str,
    mode: str,
    metrics: tuple[BenchmarkMetric, ...],
) -> BenchmarkReport:
    return BenchmarkReport(
        id=source,
        source=source,
        kind="diagnostic",
        model=model,
        mode=mode,
        context="Provenance or diagnostic; excluded from accuracy rankings",
        platform="Not applicable",
        scope="Not an accuracy or end-to-end safety measurement.",
        metrics=metrics,
    )


def _parity_reports(source: str, payload: object) -> tuple[BenchmarkReport, ...]:
    if not isinstance(payload, list) or len(payload) > 2:
        raise ValueError("Invalid parity report")
    result = []
    for index, value in enumerate(payload):
        item = mapping(value)
        report = _diagnostic(
            source,
            model_label(item.get("model")),
            "decoder_parity",
            (
                metric(
                    "Inputs compared", item.get("case_count_including_derived_inputs")
                ),
                metric("Matching inputs", item.get("matching_cases")),
                text_metric("Reference", "gliner 0.2.30 upstream wrapper"),
            ),
        )
        result.append(report.model_copy(update={"id": f"{source}:{index}"}))
    return tuple(result)


def _overhead_report(source: str, report: dict[str, object]) -> BenchmarkReport:
    idle = mapping(report.get("idle", {}))
    polling = mapping(report.get("queue_polling", {}))
    first = mapping(report.get("benchmarks_first_request", {}))
    cached = mapping(report.get("benchmarks_cached_request", {}))
    memory = mapping(report.get("memory_after_benchmarks", {}))
    lifetime = mapping(report.get("server_lifetime", {}))
    peaks = [number(item.get("peak_rss_bytes")) for item in (memory, lifetime)]
    known_peaks = [value for value in peaks if value is not None]
    ticks = number(report.get("cpu_clock_ticks_per_second"))
    imports = mapping(report.get("import_audit", {})).get("loaded_model_packages")
    metrics = (
        metric("Queued tasks", report.get("task_count")),
        metric("Startup", report.get("startup_seconds"), "seconds"),
        metric("Polling interval", report.get("poll_interval_seconds"), "seconds"),
        metric("First benchmark request", first.get("seconds"), "seconds"),
        metric("Cached benchmark request", cached.get("seconds"), "seconds"),
        metric(
            "Monitor process peak RSS", max(known_peaks) if known_peaks else None, "mib"
        ),
        metric(
            "Whole probe peak cgroup memory", report.get("cgroup_peak_bytes"), "mib"
        ),
        metric("CPU clock resolution", 1 / ticks if ticks else None, "seconds"),
        metric(
            "Loaded model packages", len(imports) if isinstance(imports, list) else None
        ),
        text_metric(
            "Memory scope",
            "Cgroup includes seeding and HTTP client; RSS is the monitor child",
        ),
        text_metric(
            "Idle CPU meaning",
            "A zero CPU counter delta means below clock resolution, not no work",
        ),
        *(
            metric(
                f"{label} CPU (one core)",
                measured / 100 if measured is not None else None,
                "percent",
            )
            for label, sample in (("Idle", idle), ("Polling", polling))
            for measured in (number(sample.get("server_cpu_percent_of_one_core")),)
        ),
        metric("Idle observation", idle.get("wall_seconds"), "seconds"),
        metric("Polling observation", polling.get("wall_seconds"), "seconds"),
        metric("Queue requests", polling.get("request_count")),
    )
    return BenchmarkReport(
        id=source,
        source=source,
        kind="diagnostic",
        model="Local dashboard",
        mode="dashboard_overhead",
        context=(
            "Parent-owned monitor process; synthetic queue overhead probe"
            if report.get("server_mode") == "parent_owned"
            else "Separate monitor process; synthetic queue overhead probe"
        ),
        platform=platform_label(report),
        scope="No concurrent pipeline or browser process; not full-system overhead.",
        metrics=metrics,
    )
