"""Own one private evaluation ledger, preserving its shared budget across models."""

import os
import sqlite3
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

from redactor.coordinator.ownership import own_run
from redactor.persistence.database import open_database
from redactor.persistence.files.registration import register_file
from redactor.persistence.models.budget import recover_model_attempts
from redactor.persistence.queue.tasks import claim_task, recover_interrupted
from redactor.schemas.persistence import Task
from redactor.utils.constants import EVALUATION_KEY_FILENAME, EVALUATION_REMOTE_VERSION


@contextmanager
def evaluation_state(
    directory: Path, source: Path, step: str
) -> Generator[tuple[sqlite3.Connection, Task, bytes], None, None]:
    with own_run(directory):
        connection = open_database(directory)
        try:
            key_path = directory / EVALUATION_KEY_FILENAME
            if not key_path.exists():
                with key_path.open("xb") as output:
                    os.chmod(key_path, 0o600)
                    output.write(os.urandom(32))
                    output.flush()
                    os.fsync(output.fileno())
            register_file(connection, source, step, EVALUATION_REMOTE_VERSION)
            recover_interrupted(connection)
            recover_model_attempts(connection)
            claimed = claim_task(
                connection, step=step, processing_version=EVALUATION_REMOTE_VERSION
            )
            assert claimed is not None
            yield connection, claimed, key_path.read_bytes()
        finally:
            connection.close()
