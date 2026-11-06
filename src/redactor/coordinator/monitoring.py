"""Best-effort dashboard lifetime without inheriting pipeline ownership locks."""

import os
import select
import subprocess
import sys
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

from redactor.utils.constants import (
    MONITOR_MODULE,
    MONITOR_READY_TOKEN,
    MONITOR_STARTUP_SECONDS,
    MONITOR_STOP_SECONDS,
)
from redactor.utils.errors import ERROR_MONITOR_STARTUP


@contextmanager
def dashboard_process(
    state_directory: Path, port: int, *, enabled: bool
) -> Generator[subprocess.Popen[bytes] | None, None, None]:
    """Startup failure is nonfatal; the coordinator retains no server resources."""
    process = start_dashboard(state_directory, port) if enabled else None
    if enabled and process is None:
        print(ERROR_MONITOR_STARTUP, file=sys.stderr)
    try:
        yield process
    finally:
        if process is not None:
            stop_dashboard(process)


def start_dashboard(state_directory: Path, port: int) -> subprocess.Popen[bytes] | None:
    process = None
    reader = writer = None
    ready = False
    try:
        reader, writer = os.pipe()
        process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                MONITOR_MODULE,
                "--state",
                str(state_directory),
                "--port",
                str(port),
                "--ready-fd",
                str(writer),
                "--parent-pid",
                str(os.getpid()),
            ],
            pass_fds=(writer,),
            close_fds=True,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        os.close(writer)
        writer = None
        readable, _, _ = select.select([reader], [], [], MONITOR_STARTUP_SECONDS)
        ready = bool(readable) and (
            os.read(reader, len(MONITOR_READY_TOKEN) + 1) == MONITOR_READY_TOKEN
            and process.poll() is None
        )
        return process if ready else None
    except (OSError, ValueError, subprocess.SubprocessError):
        return None
    finally:
        for descriptor in (reader, writer):
            if descriptor is not None:
                os.close(descriptor)
        if process is not None and not ready:
            stop_dashboard(process)


def stop_dashboard(process: subprocess.Popen[bytes]) -> None:
    """Bound the graceful stop, then kill and reap the owned child if necessary."""
    if process.poll() is None:
        try:
            process.terminate()
        except ProcessLookupError:
            pass
    try:
        process.wait(timeout=MONITOR_STOP_SECONDS)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()
