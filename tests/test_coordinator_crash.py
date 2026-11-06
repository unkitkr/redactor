import select
import subprocess
import sys
import time
from contextlib import closing
from pathlib import Path

import pytest

from redactor.coordinator.ownership import own_run
from redactor.persistence.database import open_database
from redactor.persistence.files.registration import register_file
from redactor.persistence.queue.tasks import get_task
from redactor.utils.constants import (
    BOOTSTRAP_PROCESSING_VERSION,
    PRINT_TASK_STEP,
    STATE_DIRECTORY,
    STATUS_RUNNING,
    STATUS_SUCCEEDED,
)
from redactor.utils.errors import ERROR_RUN_ACTIVE


def test_sigkill_blocks_recovery_until_surviving_worker_exits(tmp_path: Path) -> None:
    inputs = tmp_path / "input"
    inputs.mkdir()
    source = inputs / "records.txt"
    source.write_bytes(b"row\n")
    state = tmp_path / STATE_DIRECTORY
    with closing(open_database(state)) as connection:
        task = register_file(
            connection, source, PRINT_TASK_STEP, BOOTSTRAP_PROCESSING_VERSION
        )

    helper = Path(__file__).parent / "support" / "hold_claim.py"
    with subprocess.Popen(
        [sys.executable, str(helper), str(state)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
    ) as coordinator:
        assert coordinator.stdin is not None
        assert coordinator.stdout is not None
        try:
            ready, _, _ = select.select([coordinator.stdout], [], [], 5)
            assert ready, "Worker did not announce its claim"
            assert int(coordinator.stdout.readline()) > 0
            coordinator.kill()
            coordinator.wait(timeout=5)

            with pytest.raises(RuntimeError, match=ERROR_RUN_ACTIVE):
                with own_run(state):
                    pytest.fail("Recovery raced a surviving worker")
            with closing(open_database(state)) as connection:
                assert get_task(connection, task.task_id).status == STATUS_RUNNING
        finally:
            # EOF lets the surviving child exit without accepting its task.
            coordinator.stdin.close()
            if coordinator.poll() is None:
                coordinator.kill()
            coordinator.wait(timeout=5)

        deadline = time.monotonic() + 5
        while True:
            try:
                with own_run(state):
                    break
            except RuntimeError:
                assert time.monotonic() < deadline, "Worker did not release ownership"
                time.sleep(0.01)

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "redactor",
            "--input",
            str(inputs),
            "--state",
            str(state),
        ],
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 0, result.stderr
    with closing(open_database(state)) as connection:
        recovered = get_task(connection, task.task_id)
        assert recovered.status == STATUS_SUCCEEDED
        assert recovered.attempt_count == 2
