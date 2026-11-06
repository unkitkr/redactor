"""Measure the real standalone dashboard in an isolated Linux container.

Run with tools/benchmarks/run_container.py using redactor:evaluation. The
container limits and network isolation are recorded by that runner separately.
This probe records child-process use separately from the whole container peak.
"""

import argparse
import hashlib
import json
import os
import platform
import shutil
from contextlib import closing
from pathlib import Path
from tempfile import TemporaryDirectory

from dashboard_runtime import run_probe

from redactor.persistence.database import open_database
from redactor.persistence.queue.tasks import enqueue_task
from redactor.schemas.persistence import TaskSpec
from redactor.utils.constants import (
    MONITOR_BENCHMARK_DIRECTORY,
    MONITOR_SERVER_POLL_SECONDS,
    MONITOR_STEPS,
    MONITOR_TASK_STATUSES,
)


def seed_queue(state: Path, task_count: int) -> None:
    with closing(open_database(state)) as connection:
        for index in range(task_count):
            identifier = hashlib.sha256(f"synthetic-task-{index}".encode()).hexdigest()
            step = MONITOR_STEPS[index % len(MONITOR_STEPS)]
            enqueue_task(
                connection,
                TaskSpec(
                    task_id=identifier,
                    input_path=state / f"synthetic-{index}.csv",
                    input_sha256=hashlib.sha256(str(index).encode()).hexdigest(),
                    input_size=1000,
                    step=step,
                    processing_version=hashlib.sha256(
                        b"dashboard-benchmark"
                    ).hexdigest(),
                ),
            )
            connection.execute(
                "UPDATE tasks SET status = ?, attempt_count = ? WHERE task_id = ?",
                (
                    MONITOR_TASK_STATUSES[index % len(MONITOR_TASK_STATUSES)],
                    1,
                    identifier,
                ),
            )


def copy_benchmarks(source: Path, destination: Path) -> dict[str, object]:
    """Exclude prior dashboard measurements from the measured report collection."""
    digest = hashlib.sha256()
    copied = 0
    for path in sorted(
        (*source.glob("baseline-*.json"), *(source / "results").glob("*.json"))
    ):
        if path.name.startswith("dashboard-overhead"):
            continue
        relative = path.relative_to(source)
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, target)
        digest.update(str(relative).encode())
        digest.update(target.read_bytes())
        copied += 1
    return {
        "file_count": copied,
        "sha256": digest.hexdigest(),
        "exclusion": "Prior dashboard-overhead reports and container receipts",
    }


def cgroup_limits() -> dict[str, object]:
    directory = Path("/sys/fs/cgroup")
    limits: dict[str, object] = {}
    for label, filename in (
        ("cpu_max", "cpu.max"),
        ("memory_max_bytes", "memory.max"),
        ("memory_swap_max_bytes", "memory.swap.max"),
    ):
        path = directory / filename
        value = path.read_text().strip() if path.exists() else None
        limits[label] = int(value) if value and value.isdecimal() else value
    return limits


def source_fingerprint(root: Path) -> str:
    digest = hashlib.sha256()
    paths = [
        path
        for path in (root / "src").rglob("*")
        if path.is_file() and path.suffix in (".py", ".html", ".js", ".css")
    ]
    paths.extend(Path(__file__).resolve().parent.glob("dashboard*.py"))
    for path in sorted(paths):
        digest.update(str(path.relative_to(root)).encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tasks", type=int, default=1000)
    parser.add_argument("--idle-seconds", type=float, default=10)
    parser.add_argument("--poll-seconds", type=float, default=20)
    parser.add_argument("--poll-interval", type=float, default=5)
    parser.add_argument(
        "--benchmarks", type=Path, default=Path(MONITOR_BENCHMARK_DIRECTORY)
    )
    parser.add_argument("--images", type=Path, default=Path("tmp/ocr-corpus"))
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()
    if (
        platform.system() != "Linux"
        or min(
            arguments.tasks,
            arguments.idle_seconds,
            arguments.poll_seconds,
            arguments.poll_interval,
        )
        <= 0
    ):
        parser.error("Run inside Linux with positive task counts and durations.")
    root = Path.cwd().resolve()
    before_source = source_fingerprint(root)
    with TemporaryDirectory(prefix="redactor-dashboard-benchmark-") as temporary:
        state = Path(temporary)
        seed_queue(state, arguments.tasks)
        benchmark_directory = state / "benchmarks"
        benchmark_inputs = copy_benchmarks(
            arguments.benchmarks.resolve(), benchmark_directory
        )
        result = run_probe(
            state,
            benchmark_directory,
            arguments.images.resolve(),
            idle=arguments.idle_seconds,
            polling=arguments.poll_seconds,
            interval=arguments.poll_interval,
        )
    peak = Path("/sys/fs/cgroup/memory.peak")
    result.update(
        {
            "benchmark": "dashboard_overhead",
            "schema_version": 1,
            "task_count": arguments.tasks,
            "poll_interval_seconds": arguments.poll_interval,
            "server_mode": "parent_owned",
            "parent_check_interval_seconds": MONITOR_SERVER_POLL_SECONDS,
            "platform": platform.platform(),
            "python_version": platform.python_version(),
            "source_sha256": before_source,
            "source_unchanged": before_source == source_fingerprint(root),
            "revision": os.environ.get("REDACTOR_EVALUATION_REVISION"),
            "source_dirty": os.environ.get("REDACTOR_EVALUATION_DIRTY"),
            "cgroup_peak_bytes": int(peak.read_text()) if peak.exists() else None,
            "cgroup_limits": cgroup_limits(),
            "benchmark_inputs": benchmark_inputs,
            "cgroup_scope": (
                "Whole measurement container, including seeding and HTTP client"
            ),
            "cpu_clock_ticks_per_second": os.sysconf("SC_CLK_TCK"),
            "scope": "Synthetic queue; no concurrent pipeline or browser process",
        }
    )
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result), flush=True)


if __name__ == "__main__":
    main()
