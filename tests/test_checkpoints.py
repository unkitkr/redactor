"""Integration coverage for real crash recovery and a corrupted committed prefix."""

import hashlib
import signal
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

from redactor.persistence.database import state_directory
from redactor.persistence.files.checkpoints import (
    latest_checkpoint,
    resume_checkpoint,
    save_checkpoint,
)
from redactor.persistence.files.registration import register_file
from redactor.persistence.queue.tasks import claim_task, recover_interrupted
from redactor.utils.errors import ERROR_ARTIFACT_CORRUPT, ERROR_INVALID_CHECKPOINT


def test_checkpoint_survives_sigkill_and_new_attempt(
    connection: sqlite3.Connection, source_file: Path
) -> None:
    registered = register_file(connection, source_file, "rewrite", "integration-v1")
    process = subprocess.run(
        [
            sys.executable,
            str(Path(__file__).parent / "support" / "crash_after_checkpoint.py"),
            str(state_directory(connection)),
        ],
        check=False,
        timeout=10,
    )
    assert process.returncode == -signal.SIGKILL
    previous = latest_checkpoint(connection, registered.task_id)
    assert previous is not None
    recover_interrupted(connection)
    claimed = claim_task(connection)
    assert claimed is not None
    resumed = resume_checkpoint(connection, claimed, "integration-v1")
    assert resumed is not None
    prefix = b'"first\nrecord",safe\r\n'
    assert resumed.artifact_path != previous.artifact_path
    assert resumed.artifact_path.read_bytes() == prefix
    assert resumed.artifact_path.samefile(previous.artifact_path)

    completed = prefix + b"second,safe\r\n"
    resumed.artifact_path.write_bytes(completed)
    next_checkpoint = resumed.model_copy(
        update={
            "sequence": 2,
            "record_count": 2,
            "input_offset": claimed.input_size,
            "output_offset": len(completed),
            "output_prefix_sha256": hashlib.sha256(completed).hexdigest(),
            "cursor": {"record": 2},
        }
    )
    save_checkpoint(connection, claimed, next_checkpoint)
    save_checkpoint(connection, claimed, next_checkpoint)
    assert latest_checkpoint(connection, claimed.task_id) == next_checkpoint
    with pytest.raises(ValueError, match=ERROR_INVALID_CHECKPOINT):
        resume_checkpoint(connection, claimed, "different-parser")

    # A valid database record never licenses altered or truncated committed bytes.
    resumed.artifact_path.write_bytes(b"tampered")
    with pytest.raises(ValueError, match=ERROR_ARTIFACT_CORRUPT):
        resume_checkpoint(connection, claimed, "integration-v1")
