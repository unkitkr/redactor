"""Measure a full local or hosted pipeline run and exact-command replay in Linux.

Run inside a resource-limited container with input, source and models mounted
read-only. Supply REDACTOR_SECRET_KEY through the environment and retain it with
the private state. This probe never writes secrets or source content to its report.
"""

import argparse
import hashlib
import importlib.metadata
import json
import os
import platform
import sqlite3
import subprocess
import sys
from collections import Counter
from contextlib import closing
from decimal import Decimal
from pathlib import Path
from time import perf_counter, sleep
from urllib.error import URLError
from urllib.request import urlopen

from redactor.persistence.models.decisions import read_model_decision
from redactor.schemas.entities import EntityDetection
from redactor.utils.configuration import load_settings, read_mapping_key
from redactor.utils.constants import (
    DATABASE_FILENAME,
    DEFAULT_WORKER_COUNT,
    DETECTOR_OBSERVATION_CONTEXT,
    GLINER_CONFIG,
    GLINER_WEIGHTS,
    HASH_CHUNK_BYTES,
    MODEL_ENABLED_ENVIRONMENT,
    MONITOR_HOST,
    MONITOR_PORT,
    NER_GLINER,
    OUTPUT_DIRECTORY,
    REPORT_FILENAME,
    TOKENIZER_FILENAME,
)
from redactor.utils.encryption import decrypt_payload


def file_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while block := source.read(HASH_CHUNK_BYTES):
            digest.update(block)
    return digest.hexdigest()


def snapshot(directory: Path) -> dict[str, dict[str, str | int]]:
    return {
        path.relative_to(directory).as_posix(): {
            "bytes": path.stat().st_size,
            "sha256": file_digest(path),
        }
        for path in sorted(directory.rglob("*"))
        if path.is_file()
    }


def source_digest(root: Path, configuration: Path) -> str:
    digest = hashlib.sha256()
    paths = [
        path
        for path in (root / "src").rglob("*")
        if path.is_file() and path.suffix in (".py", ".sql", ".html", ".js", ".css")
    ]
    paths.extend((Path(__file__).resolve(), configuration.resolve()))
    for path in sorted(paths):
        digest.update(path.relative_to(root).as_posix().encode())
        digest.update(bytes.fromhex(file_digest(path)))
    return digest.hexdigest()


def model_fingerprint(configuration: Path) -> dict[str, object]:
    settings = load_settings(configuration).local
    if settings.ner == NER_GLINER:
        if settings.ner_directory is None:
            raise ValueError("pipeline_benchmark_missing_model_directory")
        return {
            "backend": settings.ner,
            "artifact_directory": settings.ner_directory.name,
            "artifacts": {
                str(name): {
                    "bytes": (settings.ner_directory / name).stat().st_size,
                    "sha256": file_digest(settings.ner_directory / name),
                }
                for name in (GLINER_CONFIG, TOKENIZER_FILENAME, GLINER_WEIGHTS)
            },
        }
    return {
        "backend": settings.ner,
        "package": settings.spacy_model,
        "version": importlib.metadata.version(settings.spacy_model),
    }


def queue_counts(state: Path) -> dict[str, object]:
    database = (state / DATABASE_FILENAME).resolve()
    with closing(
        sqlite3.connect(database.as_uri() + "?mode=ro", uri=True)
    ) as connection:
        connection.execute("PRAGMA query_only = ON")
        return {
            "tasks": connection.execute("SELECT count(*) FROM tasks").fetchone()[0],
            "attempts": connection.execute("SELECT count(*) FROM attempts").fetchone()[
                0
            ],
            "model_attempts": connection.execute(
                "SELECT count(*) FROM model_attempts"
            ).fetchone()[0],
            "statuses": dict(
                connection.execute("SELECT status, count(*) FROM tasks GROUP BY status")
            ),
        }


def cgroup_values() -> dict[str, str | int]:
    directory = Path("/sys/fs/cgroup")
    values: dict[str, str | int] = {}
    for filename in ("cpu.max", "memory.max", "memory.swap.max", "memory.peak"):
        value = (directory / filename).read_text().strip()
        values[filename] = int(value) if value.isdecimal() else value
    return values


def detector_accounting(state: Path) -> dict[str, object]:
    """Project encrypted evidence to counts and endpoint receipts, never its text."""
    mapping_key = read_mapping_key()
    backends: Counter[str] = Counter()
    fallbacks: Counter[str] = Counter()
    returned_models: Counter[str] = Counter()
    providers: Counter[str] = Counter()
    billed = Decimal(0)
    receipts = 0
    database = (state / DATABASE_FILENAME).resolve()
    with closing(
        sqlite3.connect(database.as_uri() + "?mode=ro", uri=True)
    ) as connection:
        connection.execute("PRAGMA query_only = ON")
        for key, encrypted in connection.execute(
            "SELECT observation_key, encrypted_payload FROM detection_observations"
        ):
            payload = decrypt_payload(
                mapping_key,
                encrypted,
                context=DETECTOR_OBSERVATION_CONTEXT + key.encode(),
            )
            observation = EntityDetection.model_validate_json(payload)
            backends.update((observation.backend,))
            if observation.fallback_reason is not None:
                fallbacks.update((observation.fallback_reason,))
        for (request_key,) in connection.execute(
            "SELECT request_key FROM model_decisions"
        ):
            decision = read_model_decision(connection, request_key, mapping_key)
            if decision is not None and decision.receipt is not None:
                receipt = decision.receipt
                returned_models.update((receipt.returned_model,))
                if receipt.provider is not None:
                    providers.update((receipt.provider,))
                if receipt.reported_cost_usd is not None:
                    billed += receipt.reported_cost_usd
                    receipts += 1
    return {
        "unique_observation_backends": dict(backends),
        "local_reasons": dict(fallbacks),
        "returned_models": dict(returned_models),
        "providers": dict(providers),
        "persisted_receipt_cost_usd": str(billed),
        "persisted_cost_receipts": receipts,
        "receipt_scope": (
            "Last completed response per durable decision; ledger covers all attempts"
        ),
    }


def execute(
    command: list[str], workspace: Path, label: str, timeout_seconds: float = 300
) -> dict[str, object]:
    started = perf_counter()
    dashboard_reachable = False
    with (
        (workspace / f"{label}.stdout").open("wb") as stdout,
        (workspace / f"{label}.stderr").open("wb") as stderr,
    ):
        process = subprocess.Popen(command, stdout=stdout, stderr=stderr)
        while process.poll() is None:
            if not dashboard_reachable:
                try:
                    url = f"http://{MONITOR_HOST}:{MONITOR_PORT}/"
                    with urlopen(url, timeout=0.1) as response:
                        dashboard_reachable = response.status == 200
                except (OSError, URLError):
                    pass
            if perf_counter() - started > timeout_seconds:
                process.kill()
                process.wait()
                raise RuntimeError("pipeline_benchmark_timeout")
            sleep(0.05)
    return {
        "exit_code": process.returncode,
        "wall_seconds": perf_counter() - started,
        "cgroup": cgroup_values(),
        "dashboard_reachable": dashboard_reachable,
        "stdout_bytes": (workspace / f"{label}.stdout").stat().st_size,
        "stderr_bytes": (workspace / f"{label}.stderr").stat().st_size,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=DEFAULT_WORKER_COUNT)
    parser.add_argument("--mode", choices=("local", "hosted"), default="local")
    parser.add_argument("--timeout-seconds", type=float, default=1800)
    arguments = parser.parse_args()
    hosted = arguments.mode == "hosted"
    if platform.system() != "Linux" or os.environ.get(MODEL_ENABLED_ENVIRONMENT) != (
        "1" if hosted else "0"
    ):
        parser.error("Use Linux and set LLM_ENABLED explicitly to match --mode.")
    if arguments.state.exists() or arguments.workers < 1:
        parser.error("Use a fresh state directory and a positive worker count.")
    workspace = arguments.state.parent
    workspace.mkdir(parents=True, exist_ok=True)
    before_inputs = snapshot(arguments.input)
    before_source = source_digest(Path.cwd(), arguments.config)
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
        str(arguments.workers),
    ]
    initial = execute(command, workspace, "initial", arguments.timeout_seconds)
    if initial["exit_code"] != 0:
        raise RuntimeError("pipeline_benchmark_initial_failed")
    output_directory = workspace / OUTPUT_DIRECTORY
    before_outputs = snapshot(output_directory)
    initial_queue = queue_counts(arguments.state)
    report = json.loads((output_directory / REPORT_FILENAME).read_text())
    replay = execute(command, workspace, "replay", arguments.timeout_seconds)
    after_queue = queue_counts(arguments.state)
    output_unchanged = before_outputs == snapshot(output_directory)
    input_unchanged = before_inputs == snapshot(arguments.input)
    source_unchanged = before_source == source_digest(Path.cwd(), arguments.config)
    queue_unchanged = initial_queue == after_queue
    names = {item["sha256"]: name for name, item in before_inputs.items()}
    files = [{"file": names[item["input_sha256"]], **item} for item in report["files"]]
    result = {
        "benchmark": "held_in_pipeline",
        "schema_version": 1,
        "scope": (
            "Supplied assignment inputs; development evidence, not held-out accuracy"
        ),
        "command": command,
        "platform": platform.platform(),
        "python_version": platform.python_version(),
        "runtime_versions": {
            name: importlib.metadata.version(name)
            for name in ("onnxruntime", "tokenizers", "spacy")
        },
        "model_mode": "hosted_with_local_fallback" if hosted else "local_only",
        "local_ner": model_fingerprint(arguments.config),
        "remote_enabled": hosted,
        "detection": detector_accounting(arguments.state),
        "requested_model": load_settings(arguments.config).remote.model
        if hosted
        else None,
        "dashboard": "Enabled; one page probe per execution, no browser workload",
        "source_sha256": before_source,
        "source_unchanged": source_unchanged,
        "configuration_sha256": file_digest(arguments.config),
        "input_files": before_inputs,
        "input_file_count": len(before_inputs),
        "input_bytes": sum(int(item["bytes"]) for item in before_inputs.values()),
        "input_unchanged": input_unchanged,
        "initial": {**initial, "queue": initial_queue},
        "replay": {
            **replay,
            "queue": after_queue,
            "output_bytes_unchanged": output_unchanged,
            "queue_counts_unchanged": queue_unchanged,
        },
        "complete": report["complete"],
        "inventoried": report["inventoried"],
        "published": report["published"],
        "quarantined": report["quarantined"],
        "quarantine_reasons": dict(
            Counter(item["reason"] for item in files if item["status"] == "quarantined")
        ),
        "files": sorted(files, key=lambda item: item["file"]),
        "memory_scope": (
            "Whole container including probe, coordinator, workers and dashboard"
        ),
        "memory_peak_is_cumulative": True,
        "crash_injection": False,
    }
    arguments.output.write_text(json.dumps(result, indent=2) + "\n")
    if replay["exit_code"] != 0 or not all(
        (
            report["complete"],
            report["inventoried"] == len(before_inputs),
            report["published"] + report["quarantined"] == len(before_inputs),
            initial_queue["statuses"] == {"succeeded": initial_queue["tasks"]},
            (initial_queue["model_attempts"] != 0)
            if hosted
            else (
                initial_queue["model_attempts"] == 0
                and all(item["cost_bound_nanos"] == 0 for item in files)
            ),
            input_unchanged,
            source_unchanged,
            output_unchanged,
            queue_unchanged,
        )
    ):
        raise RuntimeError("pipeline_benchmark_replay_failed")


if __name__ == "__main__":
    main()
