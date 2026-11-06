"""Read bounded public measurement files without accessing private model state."""

import hashlib
import json
import os
import re
from pathlib import Path

from redactor.monitoring.benchmark_metrics import mapping
from redactor.monitoring.benchmark_reports import normalize_reports
from redactor.monitoring.files import read_bounded_file
from redactor.schemas.benchmarks import (
    BenchmarkImage,
    BenchmarkIssue,
    BenchmarkReport,
    BenchmarkSnapshot,
)
from redactor.utils.constants import (
    MONITOR_BENCHMARK_FILENAME_PATTERN,
    MONITOR_BENCHMARK_IMAGE_CASE_PATTERN,
    MONITOR_BENCHMARK_IMAGE_URL_TEMPLATE,
    MONITOR_BENCHMARK_MANIFEST,
    MONITOR_MAX_BENCHMARK_BYTES,
    MONITOR_MAX_BENCHMARK_CASES,
    MONITOR_MAX_BENCHMARK_FILES,
    MONITOR_MAX_IMAGE_BYTES,
    MONITOR_MISSING,
    MONITOR_READY,
    MONITOR_UNAVAILABLE,
    PNG_SIGNATURE,
)


def read_benchmarks(directory: Path, image_directory: Path) -> BenchmarkSnapshot:
    """Discovery is limited to results JSON and top-level baseline JSON files."""
    issues: list[BenchmarkIssue] = []
    reports: list[BenchmarkReport] = []
    if not directory.exists():
        return BenchmarkSnapshot(status=MONITOR_MISSING)
    if directory.is_symlink() or not directory.is_dir():
        return BenchmarkSnapshot(
            status=MONITOR_UNAVAILABLE,
            issues=(
                BenchmarkIssue(
                    source="benchmarks", reason="Unsafe benchmark directory"
                ),
            ),
        )
    try:
        files = _discover_files(directory, issues)
    except OSError:
        return BenchmarkSnapshot(
            status=MONITOR_UNAVAILABLE,
            issues=(
                BenchmarkIssue(
                    source="benchmarks", reason="Benchmark directory is unreadable"
                ),
            ),
        )
    for path in files:
        source = path.relative_to(directory).as_posix()
        try:
            payload = json.loads(read_bounded_file(path, MONITOR_MAX_BENCHMARK_BYTES))
            reports.extend(normalize_reports(source, payload))
        except (OSError, ValueError, TypeError, RecursionError, OverflowError):
            issues.append(
                BenchmarkIssue(
                    source=source, reason="Invalid, oversized or unreadable report"
                )
            )
    hashes = {
        report.corpus_sha256
        for report in reports
        if report.kind == "ocr" and report.corpus_sha256
    }
    images = _images(image_directory, hashes, issues) if hashes else ()
    status = (
        MONITOR_READY if reports else MONITOR_UNAVAILABLE if issues else MONITOR_MISSING
    )
    return BenchmarkSnapshot(
        status=status, reports=tuple(reports), images=images, issues=tuple(issues)
    )


def _discover_files(directory: Path, issues: list[BenchmarkIssue]) -> tuple[Path, ...]:
    files: list[Path] = []
    inspected = 0
    locations = ((directory, True), (directory / "results", False))
    for parent, baseline_only in locations:
        if parent.is_symlink():
            issues.append(
                BenchmarkIssue(
                    source="results", reason="Symlinked results directory rejected"
                )
            )
            continue
        if not parent.exists():
            continue
        with os.scandir(parent) as entries:
            for entry in entries:
                if not entry.name.endswith(".json") or (
                    baseline_only and not entry.name.startswith("baseline-")
                ):
                    continue
                if inspected >= MONITOR_MAX_BENCHMARK_FILES:
                    issues.append(
                        BenchmarkIssue(
                            source="benchmarks", reason="Benchmark file limit reached"
                        )
                    )
                    return tuple(sorted(files))
                inspected += 1
                if re.fullmatch(MONITOR_BENCHMARK_FILENAME_PATTERN, entry.name) is None:
                    issues.append(
                        BenchmarkIssue(
                            source="benchmarks", reason="Invalid report filename"
                        )
                    )
                    continue
                files.append(Path(entry.path))
    return tuple(sorted(files))


def _images(
    directory: Path, hashes: set[str], issues: list[BenchmarkIssue]
) -> tuple[BenchmarkImage, ...]:
    if not directory.exists():
        return ()
    if directory.is_symlink() or not directory.is_dir():
        issues.append(
            BenchmarkIssue(source="image corpus", reason="Unsafe image directory")
        )
        return ()
    try:
        payload = read_bounded_file(
            directory / MONITOR_BENCHMARK_MANIFEST, MONITOR_MAX_BENCHMARK_BYTES
        )
        if hashlib.sha256(payload).hexdigest() not in hashes:
            issues.append(
                BenchmarkIssue(
                    source="image corpus",
                    reason="Manifest does not match the measured corpus",
                )
            )
            return ()
        manifest = json.loads(payload)
        if (
            not isinstance(manifest, list)
            or len(manifest) > MONITOR_MAX_BENCHMARK_CASES
        ):
            raise ValueError("Invalid manifest")
    except (OSError, ValueError, RecursionError):
        issues.append(
            BenchmarkIssue(
                source="image corpus", reason="Invalid or unreadable image manifest"
            )
        )
        return ()
    images: list[BenchmarkImage] = []
    identifiers: set[str] = set()
    root = directory.resolve()
    for item in manifest:
        try:
            identifier = mapping(item).get("case_id")
            if (
                not isinstance(identifier, str)
                or re.fullmatch(MONITOR_BENCHMARK_IMAGE_CASE_PATTERN, identifier)
                is None
                or identifier in identifiers
            ):
                raise ValueError("Invalid image identifier")
            identifiers.add(identifier)
            # The manifest's `image` value is deliberately never consulted.
            path = directory / f"{identifier}.png"
            if path.resolve().parent != root:
                raise ValueError("Image escapes corpus directory")
            if not read_bounded_file(path, MONITOR_MAX_IMAGE_BYTES).startswith(
                PNG_SIGNATURE
            ):
                raise ValueError("Invalid PNG")
            images.append(
                BenchmarkImage(
                    case_id=identifier,
                    url=MONITOR_BENCHMARK_IMAGE_URL_TEMPLATE.format(case_id=identifier),
                )
            )
        except (OSError, ValueError, TypeError):
            issues.append(
                BenchmarkIssue(
                    source="image corpus", reason="Unsafe or unavailable image omitted"
                )
            )
    return tuple(images)
