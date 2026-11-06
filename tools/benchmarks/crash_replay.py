"""Exercise two seeded process-group crashes against a completed local baseline.

Run inside the same frozen production image with identical input paths, config,
models and secret environment. Mount baseline output read-only; report only hashes
and queue metadata. Two timings are bounded integration evidence, not exhaustive
crash coverage. The caller supplies CPU, memory, swap and network limits.
"""

import argparse
import fcntl
import json
import os
import random
import signal
import sqlite3
import subprocess
import sys
from contextlib import closing
from pathlib import Path
from time import perf_counter, sleep

from pipeline import cgroup_values, snapshot

from redactor.utils.constants import (
    DATABASE_FILENAME,
    OUTPUT_DIRECTORY,
    REPORT_FILENAME,
    RUN_LOCK_FILENAME,
)


def queue_snapshot(state: Path) -> dict[str, object]:
    with closing(
        sqlite3.connect((state / DATABASE_FILENAME).as_uri() + "?mode=ro", uri=True)
    ) as connection:
        return {
            "integrity": connection.execute("PRAGMA integrity_check").fetchone()[0],
            "foreign_key_errors": len(
                connection.execute("PRAGMA foreign_key_check").fetchall()
            ),
            "tasks": connection.execute("SELECT count(*) FROM tasks").fetchone()[0],
            "task_statuses": dict(
                connection.execute("SELECT status,count(*) FROM tasks GROUP BY status")
            ),
            "attempt_statuses": dict(
                connection.execute(
                    "SELECT status,count(*) FROM attempts GROUP BY status"
                )
            ),
            "running": [
                {"file": Path(path).name, "step": step}
                for path, step in connection.execute(
                    "SELECT input_path,step FROM tasks WHERE status='running'"
                )
            ],
            "duplicate_successful_results": connection.execute(
                "SELECT count(*) FROM (SELECT task_id FROM attempts "
                "WHERE status='succeeded' GROUP BY task_id HAVING count(*)>1)"
            ).fetchone()[0],
            "model_attempts": connection.execute(
                "SELECT count(*) FROM model_attempts"
            ).fetchone()[0],
        }


def lock_available(state: Path) -> bool:
    with (state / RUN_LOCK_FILENAME).open("rb") as stream:
        try:
            fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return False
        return True


def semantic_report(path: Path) -> dict[str, object]:
    report = json.loads(path.read_text())
    for item in report["files"]:
        item.pop("duration_seconds", None)
    report["files"] = sorted(report["files"], key=lambda item: item["input_sha256"])
    return report


def live_group_members(group: int) -> list[int]:
    members = []
    for entry in Path("/proc").iterdir():
        if not entry.name.isdecimal():
            continue
        try:
            fields = (entry / "stat").read_text().split(") ", 1)[1].split()
        except (FileNotFoundError, ProcessLookupError):
            continue
        if int(fields[2]) == group and fields[0] != "Z":
            members.append(int(entry.name))
    return members


def descendant_groups(parent: int) -> list[int]:
    relations = {}
    for entry in Path("/proc").iterdir():
        if not entry.name.isdecimal():
            continue
        try:
            fields = (entry / "stat").read_text().split(") ", 1)[1].split()
        except (FileNotFoundError, ProcessLookupError):
            continue
        relations[int(entry.name)] = (int(fields[1]), int(fields[2]))
    descendants = {parent}
    while True:
        expanded = descendants | {
            pid for pid, (ppid, _) in relations.items() if ppid in descendants
        }
        if expanded == descendants:
            break
        descendants = expanded
    return sorted({relations[pid][1] for pid in descendants if pid in relations})


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=20261107)
    parser.add_argument("--timeout-seconds", type=float, default=150)
    arguments = parser.parse_args()
    if arguments.state.exists() or os.environ.get("LLM_ENABLED") != "0":
        parser.error("Use fresh state and LLM_ENABLED=0.")
    workspace = arguments.state.parent
    workspace.mkdir(parents=True, exist_ok=True)
    command = [
        sys.executable,
        "-m",
        "redactor",
        "--input",
        str(arguments.input),
        "--state",
        str(arguments.state),
        "--config",
        str(arguments.config),
        "--workers",
        "2",
    ]
    before_inputs = snapshot(arguments.input)
    rng = random.Random(arguments.seed)
    delays = [rng.uniform(3, 8), rng.uniform(3, 8)]
    crashes = []
    started = perf_counter()
    for index, delay in enumerate([*delays, None]):
        with (
            (workspace / f"crash-{index}.stdout").open("wb") as stdout,
            (workspace / f"crash-{index}.stderr").open("wb") as stderr,
        ):
            process = subprocess.Popen(
                command, stdout=stdout, stderr=stderr, start_new_session=True
            )
            run_started = perf_counter()
            if delay is None:
                process.wait(timeout=arguments.timeout_seconds)
                final_exit_code = process.returncode
                break
            sleep(delay)
            if process.poll() is not None:
                raise RuntimeError("process_exited_before_injection")
            queue = queue_snapshot(arguments.state)
            groups = descendant_groups(process.pid)
            group_members = [
                pid for group in groups for pid in live_group_members(group)
            ]
            was_locked = not lock_available(arguments.state)
            for group in groups:
                os.killpg(group, signal.SIGKILL)
            process.wait()
            for _ in range(100):
                if not any(
                    live_group_members(group) for group in groups
                ) and lock_available(arguments.state):
                    break
                sleep(0.01)
            crashes.append(
                {
                    "delay_seconds": delay,
                    "elapsed_seconds": perf_counter() - run_started,
                    "signal": "SIGKILL",
                    "process_group_count": len(groups),
                    "group_member_count": len(group_members),
                    "surviving_group_members": sum(
                        len(live_group_members(group)) for group in groups
                    ),
                    "coordinator_exit_code": process.returncode,
                    "queue_before": queue,
                    "lock_held_before": was_locked,
                    "lock_available_after": lock_available(arguments.state),
                }
            )
    output = workspace / OUTPUT_DIRECTORY
    expected = {
        name: value
        for name, value in snapshot(arguments.baseline).items()
        if name.startswith(("published/", "quarantine/"))
    }
    actual = {
        name: value
        for name, value in snapshot(output).items()
        if name.startswith(("published/", "quarantine/"))
    }
    original_report = semantic_report(arguments.baseline / REPORT_FILENAME)
    replayed_report = semantic_report(output / REPORT_FILENAME)
    final_queue = queue_snapshot(arguments.state)
    result = {
        "benchmark": "seeded_process_group_crash_replay",
        "schema_version": 1,
        "scope": "Two timings on 12 supplied files; not exhaustive crash coverage",
        "seed": arguments.seed,
        "command": command,
        "kills": crashes,
        "wall_seconds": perf_counter() - started,
        "final_exit_code": final_exit_code,
        "cgroup": cgroup_values(),
        "memory_scope": ("Whole container: helper, coordinator, workers, dashboard"),
        "input_files": before_inputs,
        "input_unchanged": before_inputs == snapshot(arguments.input),
        "all_artifact_bytes_equal": expected == actual,
        "artifact_mismatches": sorted(
            name
            for name in expected.keys() | actual.keys()
            if expected.get(name) != actual.get(name)
        ),
        "artifact_files": actual,
        "semantic_report_equal": original_report == replayed_report,
        "ignored_report_fields": ["files[].duration_seconds"],
        "final_queue": final_queue,
        "complete": replayed_report["complete"],
        "inventoried": replayed_report["inventoried"],
        "published": replayed_report["published"],
        "quarantined": replayed_report["quarantined"],
    }
    result["passed"] = all(
        (
            final_exit_code == 0,
            result["input_unchanged"],
            expected == actual,
            original_report == replayed_report,
            final_queue["integrity"] == "ok",
            final_queue["foreign_key_errors"] == 0,
            final_queue["duplicate_successful_results"] == 0,
            final_queue["model_attempts"] == 0,
            all(
                item["lock_held_before"]
                and item["lock_available_after"]
                and not item["surviving_group_members"]
                for item in crashes
            ),
        )
    )
    arguments.output.write_text(json.dumps(result, indent=2) + "\n")
    print(
        json.dumps(
            {
                key: result[key]
                for key in (
                    "passed",
                    "published",
                    "quarantined",
                    "all_artifact_bytes_equal",
                    "semantic_report_equal",
                    "artifact_mismatches",
                )
            }
        )
    )

    if not result["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
