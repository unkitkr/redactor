import sqlite3
from hashlib import sha256
from pathlib import Path

import pytest

from redactor.persistence.client import claim_task, complete_task, open_queue
from redactor.persistence.files.registration import prepare_task, register_file
from redactor.persistence.queue.tasks import get_task
from redactor.schemas.persistence import Artifact
from redactor.utils.constants import STATE_DIRECTORY, STATUS_RUNNING, STATUS_SUCCEEDED


def test_client_closes_connection_without_acknowledging_unfinished_work(
    connection: sqlite3.Connection, source_file: Path, tmp_path: Path
) -> None:
    task = register_file(connection, source_file, "inspect", "v1")
    with pytest.raises(ValueError, match="work interrupted"):
        with open_queue(tmp_path / STATE_DIRECTORY) as queue:
            assert (
                claim_task(queue, step="inspect", processing_version="v1") is not None
            )
            raise ValueError("work interrupted")

    assert get_task(connection, task.task_id).status == STATUS_RUNNING
    with pytest.raises(sqlite3.ProgrammingError, match="closed database"):
        claim_task(queue)


def test_functional_api_preserves_step_result_and_queues_the_next_step(
    connection: sqlite3.Connection, source_file: Path, tmp_path: Path
) -> None:
    register_file(connection, source_file, "inspect", "v1")
    successor = prepare_task(source_file, "rewrite", "v1")
    artifact_path = tmp_path / "inspection-result.json"
    content = b'{"record_count": 3}'
    artifact_path.write_bytes(content)
    artifact = Artifact(
        path=artifact_path, sha256=sha256(content).hexdigest(), size=len(content)
    )

    with open_queue(tmp_path / STATE_DIRECTORY) as queue:
        claimed = claim_task(queue, step="inspect", processing_version="v1")
        assert claimed is not None
        completed = complete_task(
            queue, claimed, result=artifact, successors=[successor]
        )
        assert completed.status == STATUS_SUCCEEDED
        assert completed.result_path == artifact_path
        assert completed.result_sha256 == artifact.sha256
        assert claim_task(queue, step="inspect", processing_version="v1") is None
        next_step = claim_task(queue, step="rewrite", processing_version="v1")
        assert next_step is not None
        assert next_step.task_id == successor.task_id
