"""An optional dashboard cannot own the run lock or prevent pipeline execution."""

import http.client
import json
import os
import select
import signal
import socket
import subprocess
import sys
from contextlib import ExitStack, closing
from pathlib import Path
from time import monotonic, sleep

import pytest

from redactor.coordinator import cli, monitoring
from redactor.coordinator.ownership import own_run
from redactor.coordinator.run import run_coordinator
from redactor.persistence.database import open_database
from redactor.persistence.queue.tasks import iter_tasks
from redactor.schemas.coordinator import CoordinatorConfig
from redactor.utils.constants import DATABASE_FILENAME, MONITOR_HOST


def available_port() -> int:
    with socket.socket() as listener:
        listener.bind((MONITOR_HOST, 0))
        return int(listener.getsockname()[1])


def test_dashboard_readiness_cleanup_and_run_lock_are_independent(
    tmp_path: Path,
) -> None:
    state = tmp_path / "private-state"
    port = available_port()
    process = None
    with ExitStack() as ownership:
        ownership.enter_context(own_run(state))
        with pytest.raises(RuntimeError, match="test interruption"):
            with monitoring.dashboard_process(state, port, enabled=True) as process:
                assert process is not None and process.poll() is None
                with closing(
                    http.client.HTTPConnection(MONITOR_HOST, port, timeout=2)
                ) as client:
                    client.request("GET", "/api/queue")
                    response = client.getresponse()
                    assert response.status == 200
                    assert json.loads(response.read())["status"] == "missing"
                assert not (state / DATABASE_FILENAME).exists()
                ownership.close()
                # The still-running dashboard inherited only its readiness pipe.
                with own_run(state):
                    assert process.poll() is None
                raise RuntimeError("test interruption")
    assert process is not None and process.poll() is not None
    with pytest.raises(OSError):
        socket.create_connection((MONITOR_HOST, port), timeout=0.2)


def test_dashboard_startup_failures_and_timeout_are_nonfatal_and_reaped(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with socket.socket() as occupied:
        occupied.bind((MONITOR_HOST, 0))
        occupied.listen()
        port = int(occupied.getsockname()[1])
        started = monotonic()
        with monitoring.dashboard_process(tmp_path, port, enabled=True) as process:
            assert process is None
        assert monotonic() - started < 2
        inputs = tmp_path / "input"
        inputs.mkdir()
        (inputs / "record.txt").write_text("synthetic input")
        state = tmp_path / "state"
        run_coordinator(
            CoordinatorConfig(
                input_directory=inputs,
                state_directory=state,
                worker_count=1,
                diagnostic=True,
                dashboard_enabled=True,
                dashboard_port=port,
            )
        )
        with closing(open_database(state)) as connection:
            tasks = tuple(iter_tasks(connection))
            assert len(tasks) == 1 and tasks[0].status == "succeeded"

    marker = tmp_path / "child-pid"
    module = tmp_path / "unready_dashboard.py"
    module.write_text(
        "import os, pathlib, time\n"
        f"pathlib.Path({str(marker)!r}).write_text(str(os.getpid()))\n"
        "time.sleep(30)\n"
    )
    with monkeypatch.context() as patch:
        patch.setenv("PYTHONPATH", str(tmp_path))
        patch.setattr(monitoring, "MONITOR_MODULE", "unready_dashboard")
        patch.setattr(monitoring, "MONITOR_STARTUP_SECONDS", 0.2)
        assert monitoring.start_dashboard(tmp_path, available_port()) is None
    pid = int(marker.read_text())
    with pytest.raises(ProcessLookupError):
        os.kill(pid, 0)
    with monkeypatch.context() as patch:
        patch.setattr(sys, "executable", str(tmp_path / "missing-python"))
        assert monitoring.start_dashboard(tmp_path, available_port()) is None


def test_cli_dashboard_controls_and_disabled_context(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    configurations: list[CoordinatorConfig] = []
    monkeypatch.setattr(cli, "run_coordinator", configurations.append)
    monkeypatch.setattr(
        sys,
        "argv",
        ["redactor", "--no-dashboard", "--dashboard-port", "43210"],
    )
    assert cli.main() == 0
    assert configurations[0].dashboard_enabled is False
    assert configurations[0].dashboard_port == 43210
    missing = tmp_path / "missing"
    with monitoring.dashboard_process(missing, 43210, enabled=False) as process:
        assert process is None
    assert not missing.exists()
    for port in (0, -1, 65536):
        with pytest.raises(ValueError):
            CoordinatorConfig(
                input_directory=tmp_path,
                state_directory=missing,
                dashboard_port=port,
            )


def test_dashboard_exits_after_coordinator_is_killed(tmp_path: Path) -> None:
    port = available_port()
    program = (
        "import sys\n"
        "from pathlib import Path\n"
        "from redactor.coordinator.monitoring import dashboard_process\n"
        "with dashboard_process(\n"
        "    Path(sys.argv[1]), int(sys.argv[2]), enabled=True\n"
        ") as child:\n"
        "    print(child.pid if child is not None else 0, flush=True)\n"
        "    sys.stdin.read()\n"
    )
    child_pid = 0
    slow_client = None
    with subprocess.Popen(
        [sys.executable, "-c", program, str(tmp_path), str(port)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    ) as parent:
        assert parent.stdout is not None
        try:
            readable, _, _ = select.select([parent.stdout], [], [], 3)
            assert readable
            child_pid = int(parent.stdout.readline())
            assert child_pid > 0
            slow_client = socket.create_connection((MONITOR_HOST, port), timeout=2)
            slow_client.sendall(b"GET /api/queue HTTP/1.1\r\nHost: localhost\r\n")
            sleep(0.05)
            parent.kill()
            parent.wait(timeout=2)
            deadline = monotonic() + 3
            while True:
                try:
                    with socket.create_connection((MONITOR_HOST, port), timeout=0.2):
                        pass
                except ConnectionRefusedError:
                    break
                except TimeoutError:
                    # A full accept backlog is not evidence that the server exited.
                    pass
                assert monotonic() < deadline, "Orphan dashboard kept its listener open"
                sleep(0.02)
        finally:
            if slow_client is not None:
                slow_client.close()
            if parent.poll() is None:
                parent.kill()
            parent.wait(timeout=2)
            if child_pid:
                try:
                    os.kill(child_pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
