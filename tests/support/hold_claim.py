"""Crash-test fixture: a child holds a real claim until its input pipe closes."""

import os
import subprocess
import sys
from pathlib import Path

from redactor.coordinator.ownership import own_run
from redactor.persistence.client import claim_task, open_queue


def hold_claim(state_directory: Path) -> None:
    with open_queue(state_directory) as queue:
        assert claim_task(queue) is not None
        print(os.getpid(), flush=True)
        sys.stdin.read()


def hold_run(state_directory: Path) -> None:
    with own_run(state_directory) as descriptor:
        with subprocess.Popen(
            [sys.executable, __file__, str(state_directory), "worker"],
            pass_fds=(descriptor,),
        ) as worker:
            worker.wait()


if __name__ == "__main__":
    state = Path(sys.argv[1])
    if len(sys.argv) > 2:
        hold_claim(state)
    else:
        hold_run(state)
