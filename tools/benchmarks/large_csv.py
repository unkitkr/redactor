"""Measure a complete large-CSV run without treating quarantine as throughput."""

import argparse
import csv
import fcntl
import json
import os
import platform
import signal
import sqlite3
import subprocess
import sys
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter

from pipeline import cgroup_values, file_digest, model_fingerprint, source_digest

from redactor.schemas.diagnostics import FailureDiagnostic
from redactor.utils.constants import (
    DATABASE_FILENAME,
    DEFAULT_WORKER_COUNT,
    MODEL_ENABLED_ENVIRONMENT,
    OUTPUT_DIRECTORY,
    PUBLISHED_DIRECTORY,
    REPORT_FILENAME,
    RUN_LOCK_FILENAME,
    WORKER_FAILURE_FILENAME,
)


def count_rows(path: Path) -> int:
    with path.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.reader(stream, strict=True)
        header = next(reader)
        count = 0
        for row in reader:
            if len(row) != len(header):
                raise ValueError("benchmark_output_row_width")
            count += 1
    return count


def progress(state: Path) -> dict[str, object]:
    database = state / DATABASE_FILENAME
    if not database.exists():
        return {"database_exists": False}
    with closing(
        sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True)
    ) as connection:
        return {
            "steps": [
                {"step": step, "status": status, "tasks": count}
                for step, status, count in connection.execute(
                    "SELECT step, status, count(*) FROM tasks GROUP BY step, status"
                )
            ],
            "analysis_checkpoint_rows": connection.execute(
                "SELECT COALESCE(max(record_count), 0) FROM identity_scan_progress"
            ).fetchone()[0],
            "rewrite_checkpoint_rows": connection.execute(
                "SELECT COALESCE(max(record_count), 0) FROM checkpoints"
            ).fetchone()[0],
            "model_attempts": connection.execute(
                "SELECT count(*) FROM model_attempts"
            ).fetchone()[0],
        }


def require_stopped_workers(state: Path) -> None:
    """Refuse a final snapshot while any worker retains run ownership."""
    lock_path = state / RUN_LOCK_FILENAME
    if not lock_path.exists():
        return
    descriptor = os.open(lock_path, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
    finally:
        os.close(descriptor)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--generation", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--deadline-seconds", type=float, default=1800)
    parser.add_argument("--shutdown-seconds", type=float, default=10)
    parser.add_argument("--image-id", default="")
    arguments = parser.parse_args()
    if platform.system() != "Linux" or os.environ.get(MODEL_ENABLED_ENVIRONMENT) != "0":
        parser.error("Use Linux with LLM_ENABLED=0.")
    if (
        arguments.state.exists()
        or arguments.deadline_seconds <= 0
        or arguments.shutdown_seconds <= 0
    ):
        parser.error("Use fresh state and positive deadlines.")
    workspace = arguments.state.parent
    workspace.mkdir(parents=True, exist_ok=True)
    generation = json.loads(arguments.generation.read_text())
    source_before = source_digest(Path.cwd(), arguments.config)
    command = [
        sys.executable,
        "-m",
        "redactor",
        "--input",
        str(arguments.input.parent),
        "--state",
        str(arguments.state),
        "--config",
        str(arguments.config),
        "--workers",
        str(DEFAULT_WORKER_COUNT),
    ]
    timed_out = False
    termination_started_at: str | None = None
    with (
        (workspace / "pipeline.stdout").open("wb") as stdout,
        (workspace / "pipeline.stderr").open("wb") as stderr,
    ):
        started = perf_counter()
        process = subprocess.Popen(
            command, stdout=stdout, stderr=stderr, start_new_session=True
        )
        try:
            process.wait(timeout=arguments.deadline_seconds)
        except subprocess.TimeoutExpired:
            timed_out = True
            termination_started_at = datetime.now(UTC).isoformat()
            process.terminate()
            try:
                process.wait(timeout=arguments.shutdown_seconds)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()
        elapsed = perf_counter() - started
    process_stopped_at = datetime.now(UTC).isoformat()
    limits = cgroup_values()
    memory_events = {
        key: int(value)
        for key, value in (
            line.split()
            for line in Path("/sys/fs/cgroup/memory.events").read_text().splitlines()
        )
    }
    require_stopped_workers(arguments.state)
    report_path = workspace / OUTPUT_DIRECTORY / REPORT_FILENAME
    report = json.loads(report_path.read_text()) if report_path.exists() else None
    published = (
        workspace / OUTPUT_DIRECTORY / PUBLISHED_DIRECTORY / arguments.input.name
    )
    published_rows = count_rows(published) if published.exists() else 0
    complete_coverage = (
        process.returncode == 0
        and report is not None
        and report["published"] == 1
        and report["quarantined"] == 0
        and published_rows == generation["input_rows"]
    )
    quota, period = str(limits["cpu.max"]).split()
    requested_memory_bytes = 1_000_000_000
    page_size = os.sysconf("SC_PAGE_SIZE")
    effective_memory_bytes = requested_memory_bytes // page_size * page_size
    resource_gate = (
        quota != "max"
        and int(quota) == 2 * int(period)
        and limits["memory.max"] == effective_memory_bytes
        and limits["memory.swap.max"] == 0
    )
    full_target = generation["input_bytes"] >= 2 * 1024**3 and resource_gate
    source_unchanged = source_before == source_digest(Path.cwd(), arguments.config)
    input_unchanged = file_digest(arguments.input) == generation["input_sha256"]
    result = {
        "measurement": "large_csv_pipeline",
        "generator": generation,
        "command": command,
        "platform": platform.platform(),
        "python_version": platform.python_version(),
        "model_mode": "local_only",
        "local_ner": model_fingerprint(arguments.config),
        "source_sha256": source_before,
        "source_unchanged": source_unchanged,
        "image_id": arguments.image_id,
        "probe_sha256": file_digest(Path(__file__)),
        "configuration_sha256": file_digest(arguments.config),
        "input_unchanged": input_unchanged,
        "exit_code": process.returncode,
        "timed_out": timed_out,
        "termination_started_at": termination_started_at,
        "process_stopped_at": process_stopped_at,
        "workers_stopped_before_snapshot": True,
        "deadline_seconds": arguments.deadline_seconds,
        "wall_seconds": elapsed,
        "cgroup": limits,
        "requested_memory_limit_bytes": requested_memory_bytes,
        "page_size_bytes": page_size,
        "cgroup_memory_events": memory_events,
        "memory_scope": "Entire container, including probe, workers and dashboard",
        "stdout_bytes": (workspace / "pipeline.stdout").stat().st_size,
        "stderr_bytes": (workspace / "pipeline.stderr").stat().st_size,
        "progress": progress(arguments.state),
        "state_bytes": sum(
            path.stat().st_size for path in arguments.state.rglob("*") if path.is_file()
        ),
        "worker_failures": [
            FailureDiagnostic.model_validate_json(path.read_bytes()).model_dump()
            for path in arguments.state.glob(WORKER_FAILURE_FILENAME.format(pid="*"))
        ],
        "report": report,
        "published_rows": published_rows,
        "all_rows_published": complete_coverage,
        "publication_rows_per_second": published_rows / elapsed,
        "completed_input_mib_per_second": (
            generation["input_bytes"] / 1024**2 / elapsed if complete_coverage else None
        ),
        "full_acceptance_target_exercised": full_target,
        "acceptance_passed": (
            full_target
            and complete_coverage
            and elapsed <= 1800
            and source_unchanged
            and input_unchanged
            and int(limits["memory.peak"]) <= 1_000_000_000
        ),
        "scope": (
            "One complete generated CSV; a quarantine outcome is not complete "
            "row processing and cannot establish redaction throughput."
        ),
    }
    arguments.output.write_text(json.dumps(result, indent=2) + "\n")


if __name__ == "__main__":
    main()
