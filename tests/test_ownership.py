import subprocess
import sys
from pathlib import Path

import pytest

from redactor.coordinator.ownership import own_run
from redactor.utils.constants import RUN_LOCK_FILENAME, STATE_DIRECTORY
from redactor.utils.errors import ERROR_RUN_ACTIVE


def test_run_ownership_is_exclusive_and_released_after_error(tmp_path: Path) -> None:
    state_directory = tmp_path / STATE_DIRECTORY
    with pytest.raises(ValueError, match="interrupted startup"):
        with own_run(state_directory):
            with pytest.raises(RuntimeError, match=ERROR_RUN_ACTIVE):
                with own_run(state_directory):
                    pytest.fail("A second coordinator acquired ownership")
            raise ValueError("interrupted startup")

    with own_run(state_directory):
        assert (state_directory / RUN_LOCK_FILENAME).stat().st_mode & 0o777 == 0o600


def test_surviving_worker_keeps_ownership_until_it_exits(tmp_path: Path) -> None:
    state_directory = tmp_path / STATE_DIRECTORY
    worker: subprocess.Popen[str] | None = None
    try:
        with own_run(state_directory) as descriptor:
            worker = subprocess.Popen(
                [
                    sys.executable,
                    "-c",
                    "import sys; print('ready', flush=True); sys.stdin.read()",
                ],
                pass_fds=(descriptor,),
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                text=True,
            )
            assert worker.stdout is not None
            assert worker.stdout.readline().strip() == "ready"

        with pytest.raises(RuntimeError, match=ERROR_RUN_ACTIVE):
            with own_run(state_directory):
                pytest.fail("Surviving worker lost run ownership")

        worker.kill()
        worker.communicate(timeout=5)
        with own_run(state_directory):
            pass
    finally:
        if worker is not None:
            if worker.poll() is None:
                worker.kill()
            worker.communicate(timeout=5)
