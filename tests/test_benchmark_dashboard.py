"""Serve measured summaries and a bounded, corpus-matched image allowlist."""

import hashlib
import json
from pathlib import Path
from typing import cast

from PIL import Image

from redactor.monitoring.benchmarks import read_benchmarks
from redactor.schemas.benchmarks import BenchmarkReport
from redactor.utils.constants import (
    MONITOR_MAX_BENCHMARK_BYTES,
    MONITOR_MAX_BENCHMARK_FILES,
    MONITOR_MAX_IMAGE_BYTES,
)


def _metric(report: BenchmarkReport, label: str) -> int | float | str | None:
    return next(item.value for item in report.metrics if item.label == label)


def _ocr_report() -> dict[str, object]:
    path = Path(__file__).resolve().parents[1] / "benchmarks/results/ppocr-en.json"
    return cast(dict[str, object], json.loads(path.read_text()))


def test_real_reports_keep_accuracy_replay_and_diagnostics_separate(
    tmp_path: Path,
) -> None:
    directory = Path(__file__).resolve().parents[1] / "benchmarks"
    snapshot = read_benchmarks(directory, tmp_path / "absent-images")
    assert snapshot.status == "ready" and not snapshot.issues
    text = [item for item in snapshot.reports if item.kind == "text"]
    assert len(text) == 28
    assert all(item.case_count == 40 for item in text)
    assert len([item for item in snapshot.reports if item.kind == "ocr"]) == 6

    current = next(
        item
        for item in text
        if item.id == "results/verifier-v3-glm-flash.json:combined_text_policy"
    )
    assert current.verifier_version == "verifier-v3"
    assert "fallback" in current.context and "rescoring" in current.context
    assert _metric(current, "False accepts") == 0
    assert _metric(current, "Cache misses") == 3
    assert _metric(current, "New model requests") == 0
    assert _metric(current, "Peak cgroup memory") is None
    historical = next(
        item for item in text if item.id == "results/glm-flash.json:raw_ner"
    )
    assert _metric(historical, "F1") == 0.75
    elapsed = _metric(historical, "Evaluation time")
    assert isinstance(elapsed, (int, float)) and elapsed > 100

    excluded = next(
        item
        for item in snapshot.reports
        if item.source == "results/nvidia-preflight.json"
    )
    rejected = next(
        item
        for item in snapshot.reports
        if item.source == "results/glm-flash-rejected.json"
    )
    assert excluded.kind == rejected.kind == "diagnostic"
    assert not excluded.cases and not rejected.cases
    baseline = next(item for item in snapshot.reports if item.kind == "throughput")
    assert _metric(baseline, "Rows") == 30000
    assert "not the 2 GiB" in baseline.scope
    encoded = snapshot.model_dump_json()
    assert "Elena Marlow" not in encoded and "reference_text" not in encoded


def test_bad_or_unbounded_reports_fail_without_exposing_payloads(
    tmp_path: Path,
) -> None:
    directory = tmp_path / "benchmarks"
    results = directory / "results"
    results.mkdir(parents=True)
    valid = _ocr_report()
    valid.update(model="PRIVATE_MODEL_PAYLOAD", scope="PRIVATE_SCOPE_PAYLOAD")
    (results / "ppocr-en.json").write_text(json.dumps(valid))
    (results / "broken.json").write_text('{"secret": "PRIVATE_RAW_PAYLOAD"')
    (results / "oversized.json").write_bytes(b" " * (MONITOR_MAX_BENCHMARK_BYTES + 1))
    (results / "linked.json").symlink_to(results / "ppocr-en.json")
    (directory / "private.json").write_text('{"private": "PRIVATE_TOP_LEVEL"}')
    nested = results / "nested"
    nested.mkdir()
    (nested / "private.json").write_text('{"private": "PRIVATE_NESTED"}')

    snapshot = read_benchmarks(directory, tmp_path / "images")
    assert snapshot.status == "ready" and len(snapshot.reports) == 1
    assert {issue.source for issue in snapshot.issues} == {
        "results/broken.json",
        "results/oversized.json",
        "results/linked.json",
    }
    assert "PRIVATE_" not in snapshot.model_dump_json()
    assert read_benchmarks(tmp_path / "missing", tmp_path).status == "missing"

    limited = tmp_path / "limited"
    limited.mkdir()
    for index in range(MONITOR_MAX_BENCHMARK_FILES + 1):
        (limited / f"baseline-{index}.json").write_text("{}")
    limited_snapshot = read_benchmarks(limited, tmp_path / "images")
    assert len(limited_snapshot.issues) == MONITOR_MAX_BENCHMARK_FILES + 1
    assert any("limit" in issue.reason for issue in limited_snapshot.issues)


def test_fractional_rates_and_missing_measurements_keep_their_meaning(
    tmp_path: Path,
) -> None:
    results = tmp_path / "results"
    results.mkdir()
    ocr = _ocr_report()
    evaluation = cast(dict[str, object], ocr["evaluation"])
    evaluation["character_error_rate"] = 1.5
    ocr.pop("peak_cgroup_bytes")
    (results / "ppocr-en.json").write_text(json.dumps(ocr))
    replay = {
        "model": "z-ai/glm-5.3-flash",
        "offline_replay": True,
        "evaluations": [
            {
                "mode": "combined_text_policy",
                "cases": [],
                "exact_typed_span_counts": {
                    "precision": None,
                    "recall": 1.2,
                    "f1": 0.75,
                },
                "totals": {},
            }
        ],
    }
    (results / "verifier-v3-glm-flash.json").write_text(json.dumps(replay))
    snapshot = read_benchmarks(tmp_path, tmp_path / "absent-images")
    assert snapshot.status == "ready" and not snapshot.issues
    image_report = next(item for item in snapshot.reports if item.kind == "ocr")
    assert _metric(image_report, "Character error rate") == 1.5
    assert _metric(image_report, "Peak cgroup memory") is None
    text = next(item for item in snapshot.reports if item.kind == "text")
    for label in (
        "Precision",
        "Recall",
        "Cache hits",
        "Local fallbacks",
        "New model requests",
        "New model charges (USD)",
        "Evaluation time",
        "Peak process RSS",
    ):
        assert _metric(text, label) is None
    assert _metric(text, "F1") == 0.75
    # Omitted entries in a present legacy totals Counter represent zero.
    assert _metric(text, "False accepts") == 0


def test_dashboard_overhead_keeps_process_and_probe_measurements_separate(
    tmp_path: Path,
) -> None:
    results = tmp_path / "results"
    results.mkdir()
    payload = {
        "benchmark": "dashboard_overhead",
        "server_mode": "parent_owned",
        "task_count": 1000,
        "startup_seconds": 0.3,
        "poll_interval_seconds": 5,
        "platform": "Linux-test-platform",
        "idle": {"server_cpu_percent_of_one_core": 0, "wall_seconds": 10},
        "queue_polling": {
            "server_cpu_percent_of_one_core": 0.8,
            "wall_seconds": 20,
            "request_count": 4,
        },
        "benchmarks_first_request": {"seconds": 0.35},
        "benchmarks_cached_request": {"seconds": 0.008},
        "memory_after_benchmarks": {"peak_rss_bytes": 45 * 1024 * 1024},
        "server_lifetime": {"peak_rss_bytes": 44 * 1024 * 1024},
        "cgroup_peak_bytes": 64 * 1024 * 1024,
        "cpu_clock_ticks_per_second": 100,
        "import_audit": {"loaded_model_packages": []},
    }
    (results / "dashboard-overhead.json").write_text(json.dumps(payload))
    snapshot = read_benchmarks(tmp_path, tmp_path / "absent-images")
    assert snapshot.status == "ready" and not snapshot.issues
    report = snapshot.reports[0]
    assert report.kind == "diagnostic" and "Parent-owned" in report.context
    assert "No concurrent pipeline or browser" in report.scope
    assert _metric(report, "Idle CPU (one core)") == 0
    assert _metric(report, "Polling CPU (one core)") == 0.008
    assert _metric(report, "CPU clock resolution") == 0.01
    assert _metric(report, "Monitor process peak RSS") == 45
    assert _metric(report, "Whole probe peak cgroup memory") == 64
    assert _metric(report, "First benchmark request") == 0.35
    assert _metric(report, "Cached benchmark request") == 0.008
    assert _metric(report, "Queued tasks") == 1000


def test_image_links_require_matching_manifest_and_safe_local_pngs(
    tmp_path: Path,
) -> None:
    directory = tmp_path / "benchmarks"
    results = directory / "results"
    results.mkdir(parents=True)
    images = tmp_path / "images"
    images.mkdir()
    outside = tmp_path / "outside.png"
    Image.new("RGB", (2, 2), "white").save(outside)
    Image.new("RGB", (2, 2), "white").save(images / "synthetic-1-clean.png")
    (images / "synthetic-1-rotated.png").symlink_to(outside)
    (images / "synthetic-1-blurred.png").write_bytes(b"not a PNG")
    (images / "wristband-clean.png").write_bytes(b" " * (MONITOR_MAX_IMAGE_BYTES + 1))
    manifest = [
        {
            "case_id": identifier,
            "image": "../../private.env",
            "reference_text": "PRIVATE_IMAGE_TEXT",
        }
        for identifier in (
            "synthetic-1-clean",
            "synthetic-1-rotated",
            "synthetic-1-blurred",
            "wristband-clean",
            "../../outside",
            "unapproved-clean",
        )
    ]
    manifest_path = images / "manifest.json"
    manifest_path.write_text(json.dumps(manifest))
    report = _ocr_report()
    report["corpus_sha256"] = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    (results / "ppocr-en.json").write_text(json.dumps(report))

    snapshot = read_benchmarks(directory, images)
    assert [(image.case_id, image.url) for image in snapshot.images] == [
        ("synthetic-1-clean", "/benchmark-images/synthetic-1-clean.png")
    ]
    assert len(snapshot.issues) == 5
    assert "PRIVATE_IMAGE_TEXT" not in snapshot.model_dump_json()
    manifest_path.write_text("[]")
    stale = read_benchmarks(directory, images)
    assert not stale.images and any(
        "does not match" in issue.reason for issue in stale.issues
    )

    manifest_path.unlink()
    manifest_path.symlink_to(outside)
    assert not read_benchmarks(directory, images).images
