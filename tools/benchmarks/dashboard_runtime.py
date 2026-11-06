"""Measure the dashboard child process without loading pipeline models."""

import json
import os
import resource
import select
import signal
import subprocess
import sys
from pathlib import Path
from time import monotonic, perf_counter, sleep
from urllib.request import urlopen

from redactor.utils.constants import MONITOR_BENCHMARK_CACHE_SECONDS, MONITOR_HOST


def child_cpu(pid: int) -> float:
    # /proc comm may contain spaces, so split after its closing parenthesis.
    fields = Path(f"/proc/{pid}/stat").read_text().rsplit(") ", 1)[1].split()
    return (int(fields[11]) + int(fields[12])) / os.sysconf("SC_CLK_TCK")


def child_memory(pid: int) -> dict[str, int]:
    fields = {}
    for line in Path(f"/proc/{pid}/status").read_text().splitlines():
        key, _, value = line.partition(":")
        if key in ("VmRSS", "VmHWM"):
            fields[key] = int(value.split()[0]) * 1024
    return {"rss_bytes": fields["VmRSS"], "peak_rss_bytes": fields["VmHWM"]}


def measured_request(url: str, *, json_response: bool = True) -> dict[str, object]:
    started = perf_counter()
    with urlopen(url, timeout=10) as response:
        payload = response.read()
        status = response.status
    elapsed = perf_counter() - started
    result: dict[str, object] = {
        "seconds": elapsed,
        "status": status,
        "response_bytes": len(payload),
    }
    if json_response:
        snapshot = json.loads(payload)
        if snapshot.get("status") != "ready":
            raise RuntimeError("dashboard_snapshot_not_ready")
        if "reports" in snapshot:
            result["report_count"] = len(snapshot["reports"])
        if "task_count" in snapshot:
            result["task_count"] = snapshot["task_count"]
    return result


def measure_phase(
    process: subprocess.Popen[str], seconds: float, url: str | None, interval: float
) -> dict[str, object]:
    before_cpu = child_cpu(process.pid)
    started = perf_counter()
    requests = []
    next_request = started
    while perf_counter() - started < seconds:
        if process.poll() is not None:
            raise RuntimeError("dashboard_exited_during_measurement")
        if url is not None and perf_counter() >= next_request:
            requests.append(measured_request(url))
            next_request += interval
        remaining = started + seconds - perf_counter()
        if remaining > 0:
            sleep(
                min(remaining, max(0.01, next_request - perf_counter()))
                if url
                else remaining
            )
    elapsed = perf_counter() - started
    cpu = child_cpu(process.pid) - before_cpu
    return {
        "wall_seconds": elapsed,
        "server_cpu_seconds": cpu,
        "server_cpu_percent_of_one_core": cpu / elapsed * 100,
        "request_count": len(requests),
        "requests": requests,
        **child_memory(process.pid),
    }


def run_probe(
    state: Path,
    benchmarks: Path,
    images: Path,
    *,
    idle: float,
    polling: float,
    interval: float,
) -> dict[str, object]:
    audit = state / "import-audit.json"
    # Execute the unmodified CLI and inspect imports only after it has stopped.
    launcher = """
import json, runpy, sys
from pathlib import Path
audit = Path(sys.argv.pop(1))
sys.argv[0] = "redactor.monitoring"
try:
    runpy.run_module("redactor.monitoring", run_name="__main__")
finally:
    packages = ("torch", "spacy", "onnxruntime", "paddle", "transformers",
                "rapidocr", "cv2", "numpy", "tokenizers")
    audit.write_text(json.dumps({
        "checked_packages": packages,
        "loaded_model_packages": [name for name in packages if name in sys.modules]
    }))
"""
    started = perf_counter()
    process = subprocess.Popen(
        [
            sys.executable,
            "-c",
            launcher,
            str(audit),
            "--state",
            str(state),
            "--benchmarks",
            str(benchmarks),
            "--images",
            str(images),
            "--host",
            MONITOR_HOST,
            "--port",
            "0",
            "--parent-pid",
            str(os.getpid()),
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        if process.stdout is None or not select.select([process.stdout], [], [], 15)[0]:
            raise RuntimeError("dashboard_startup_timeout")
        announcement = process.stdout.readline().strip()
        if not announcement.startswith(f"Dashboard: http://{MONITOR_HOST}:"):
            raise RuntimeError("dashboard_startup_failed")
        url = announcement.removeprefix("Dashboard: ")
        startup_seconds = perf_counter() - started
        initial_request = measured_request(url, json_response=False)
        result: dict[str, object] = {
            "startup_seconds": startup_seconds,
            "initial_page_request": initial_request,
            "idle": measure_phase(process, idle, None, interval),
            "queue_polling": measure_phase(
                process, polling, url + "/api/queue", interval
            ),
        }
        bucket = int(monotonic() / MONITOR_BENCHMARK_CACHE_SECONDS)
        result["benchmarks_first_request"] = measured_request(url + "/api/benchmarks")
        result["benchmarks_cached_request"] = measured_request(url + "/api/benchmarks")
        result["benchmark_requests_same_cache_interval"] = bucket == int(
            monotonic() / MONITOR_BENCHMARK_CACHE_SECONDS
        )
        result["memory_after_benchmarks"] = child_memory(process.pid)
    finally:
        if process.poll() is None:
            process.send_signal(signal.SIGINT)
        try:
            process.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.communicate()
    if process.returncode:
        raise RuntimeError("dashboard_shutdown_failed")
    usage = resource.getrusage(resource.RUSAGE_CHILDREN)
    result["server_lifetime"] = {
        "user_cpu_seconds": usage.ru_utime,
        "system_cpu_seconds": usage.ru_stime,
        "peak_rss_bytes": usage.ru_maxrss * 1024,
    }
    result["import_audit"] = json.loads(audit.read_text())
    return result
