import os
import select
import signal
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path

import pytest

from redactor.coordinator.ownership import own_run
from redactor.coordinator.processes import run_workers
from redactor.coordinator.signals import handle_shutdown_signals
from redactor.utils.constants import SIGNAL_EXIT_BASE, STATE_DIRECTORY


@pytest.mark.parametrize(
    ("failure", "expected_error"),
    [("launch", OSError), ("exit", RuntimeError), ("signal", SystemExit)],
)
def test_worker_group_is_reaped_after_startup_failure_or_shutdown(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure: str,
    expected_error: type[BaseException],
) -> None:
    real_popen = subprocess.Popen
    children: list[subprocess.Popen[bytes]] = []
    previous_handler = signal.getsignal(signal.SIGTERM)

    def start_child(
        command: Sequence[str],
        *,
        pass_fds: tuple[int, ...],
        stdin: int,
        start_new_session: bool,
    ) -> subprocess.Popen[bytes]:
        if children:
            if failure == "launch":
                raise OSError("failed to start second worker")
            if failure == "signal":
                os.kill(os.getpid(), signal.SIGTERM)
            script = "raise SystemExit(9)"
        else:
            script = (
                "import signal; "
                "signal.signal(signal.SIGTERM, signal.SIG_IGN); "
                "print('ready', flush=True); signal.pause()"
            )

        child = real_popen(
            [sys.executable, "-c", script],
            pass_fds=pass_fds,
            stdin=stdin,
            stdout=subprocess.PIPE,
            start_new_session=start_new_session,
        )
        children.append(child)
        if len(children) == 1:
            assert child.stdout is not None
            ready, _, _ = select.select([child.stdout], [], [], 5)
            assert ready, "Test worker did not start"
            assert child.stdout.readline().strip() == b"ready"
        return child

    monkeypatch.setattr("redactor.coordinator.processes.subprocess.Popen", start_child)
    monkeypatch.setattr("redactor.coordinator.processes.WORKER_SHUTDOWN_SECONDS", 0.05)
    state = tmp_path / STATE_DIRECTORY
    try:
        with pytest.raises(expected_error) as error:
            with handle_shutdown_signals(), own_run(state) as descriptor:
                run_workers(state, 2, descriptor)

        assert children[0].returncode == -signal.SIGKILL
        assert all(child.poll() is not None for child in children)
        if isinstance(error.value, SystemExit):
            assert error.value.code == SIGNAL_EXIT_BASE + signal.SIGTERM
        assert signal.getsignal(signal.SIGTERM) == previous_handler
        with own_run(state):
            pass
    finally:
        for child in children:
            if child.poll() is None:
                child.kill()
            child.communicate(timeout=5)
