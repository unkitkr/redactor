"""Start fresh worker interpreters and reap every child before normal exit."""

import os
import subprocess
import sys
import time
from collections.abc import Sequence
from pathlib import Path

from redactor.utils.constants import (
    EXIT_SUCCESS,
    WORKER_MODULE,
    WORKER_POLL_SECONDS,
    WORKER_SHUTDOWN_SECONDS,
)
from redactor.utils.errors import ERROR_WORKER_FAILED


def run_workers(state_directory: Path, worker_count: int, lock_descriptor: int) -> None:
    """Wait for all workers; a failed launch or worker stops the entire group."""
    workers: list[subprocess.Popen[bytes]] = []
    try:
        for _ in range(worker_count):
            workers.append(
                subprocess.Popen(
                    [
                        sys.executable,
                        "-m",
                        WORKER_MODULE,
                        str(state_directory),
                        str(os.getpid()),
                        str(lock_descriptor),
                    ],
                    pass_fds=(lock_descriptor,),
                    stdin=subprocess.DEVNULL,
                    start_new_session=True,
                )
            )

        while True:
            exit_codes = [worker.poll() for worker in workers]
            if any(code not in (None, EXIT_SUCCESS) for code in exit_codes):
                raise RuntimeError(ERROR_WORKER_FAILED)
            if all(code == EXIT_SUCCESS for code in exit_codes):
                return
            time.sleep(WORKER_POLL_SECONDS)
    finally:
        stop_workers(workers)


def stop_workers(workers: Sequence[subprocess.Popen[bytes]]) -> None:
    """Give the group a bounded grace period, then kill and reap stragglers."""
    for worker in workers:
        if worker.poll() is None:
            worker.terminate()

    deadline = time.monotonic() + WORKER_SHUTDOWN_SECONDS
    for worker in workers:
        try:
            worker.wait(timeout=max(0, deadline - time.monotonic()))
        except subprocess.TimeoutExpired:
            worker.kill()

    for worker in workers:
        worker.wait()
