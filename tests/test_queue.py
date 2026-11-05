import sqlite3
from contextlib import closing
from pathlib import Path

import pytest

from redactor.persistence.database import open_database
from redactor.persistence.files import prepare_task
from redactor.persistence.queue import (
    claim_task,
    complete_task,
    enqueue_task,
    fail_task,
    get_task,
    iter_attempts,
    iter_tasks,
    recover_interrupted,
    require_attempt,
    retry_task,
)
from redactor.schemas.persistence import Artifact
from redactor.utils.constants import (
    ERROR_COMPLETION_CHANGED,
    ERROR_DEPENDENCIES_CHANGED,
    ERROR_INVALID_FAILURE_CODE,
    ERROR_INVALID_TRANSITION,
    ERROR_PROCESSING,
    ERROR_STALE_ATTEMPT,
    ERROR_TASK_ID_CONFLICT,
    ERROR_TASK_NOT_FOUND,
    ERROR_UNKNOWN_DEPENDENCY,
    STATE_DIRECTORY,
    STATUS_FAILED,
    STATUS_INTERRUPTED,
    STATUS_PENDING,
    STATUS_RUNNING,
    STATUS_SUCCEEDED,
)


def test_rediscovery_is_idempotent(
    connection: sqlite3.Connection, source_file: Path
) -> None:
    spec = prepare_task(source_file, "inspect", "v1")
    first = enqueue_task(connection, spec)
    assert enqueue_task(connection, spec) == first
    assert list(iter_tasks(connection)) == [first]
    assert first.status == STATUS_PENDING


def test_input_step_and_configuration_define_task_identity(source_file: Path) -> None:
    original = prepare_task(source_file, "inspect", "v1")
    assert prepare_task(source_file, "inspect", "v1") == original
    assert prepare_task(source_file, "rewrite", "v1").task_id != original.task_id
    assert prepare_task(source_file, "inspect", "v2").task_id != original.task_id
    source_file.write_bytes(b"changed")
    assert prepare_task(source_file, "inspect", "v1").task_id != original.task_id


def test_reused_id_cannot_change_task_metadata(
    connection: sqlite3.Connection, source_file: Path
) -> None:
    spec = prepare_task(source_file, "inspect", "v1")
    enqueue_task(connection, spec)
    with pytest.raises(ValueError, match=ERROR_TASK_ID_CONFLICT):
        enqueue_task(connection, spec.model_copy(update={"step": "rewrite"}))


def test_claim_is_exclusive_and_records_attempt(
    connection: sqlite3.Connection, source_file: Path
) -> None:
    spec = prepare_task(source_file, "inspect", "v1")
    enqueue_task(connection, spec)
    task = claim_task(connection)
    assert task is not None
    assert task.status == STATUS_RUNNING
    assert task.attempt_token
    assert task.attempt_count == 1
    assert claim_task(connection) is None
    (attempt,) = iter_attempts(connection, task.task_id)
    assert attempt.attempt_token == task.attempt_token
    assert attempt.status == STATUS_RUNNING


def test_completed_task_is_not_dispatched_again(
    connection: sqlite3.Connection, source_file: Path
) -> None:
    spec = prepare_task(source_file, "inspect", "v1")
    enqueue_task(connection, spec)
    task = claim_task(connection)
    assert task is not None
    completed = complete_task(connection, task)
    assert complete_task(connection, task) == completed
    assert enqueue_task(connection, spec) == completed
    assert claim_task(connection) is None
    (attempt,) = iter_attempts(connection, task.task_id)
    assert attempt.status == STATUS_SUCCEEDED
    assert attempt.finished_at is not None


def test_repeated_completion_cannot_replace_result(
    connection: sqlite3.Connection, source_file: Path
) -> None:
    enqueue_task(connection, prepare_task(source_file, "inspect", "v1"))
    task = claim_task(connection)
    assert task is not None
    complete_task(connection, task)
    with pytest.raises(ValueError, match=ERROR_COMPLETION_CHANGED):
        complete_task(
            connection, task, result=Artifact(path=source_file, sha256="other", size=0)
        )
    with pytest.raises(ValueError, match=ERROR_COMPLETION_CHANGED):
        complete_task(
            connection, task, successors=[prepare_task(source_file, "rewrite", "v1")]
        )


def test_dependencies_gate_claims(
    connection: sqlite3.Connection, source_file: Path
) -> None:
    first = enqueue_task(connection, prepare_task(source_file, "inspect", "v1"))
    second = enqueue_task(
        connection,
        prepare_task(source_file, "rewrite", "v1"),
        dependencies=[first.task_id],
    )
    claimed = claim_task(connection)
    assert claimed is not None
    assert claimed.task_id == first.task_id
    assert claim_task(connection) is None
    complete_task(connection, claimed)
    next_task = claim_task(connection)
    assert next_task is not None
    assert next_task.task_id == second.task_id


def test_completion_creates_successor_atomically(
    connection: sqlite3.Connection, source_file: Path
) -> None:
    enqueue_task(connection, prepare_task(source_file, "inspect", "v1"))
    task = claim_task(connection)
    assert task is not None
    successor = prepare_task(source_file, "rewrite", "v1")
    complete_task(connection, task, successors=[successor])
    complete_task(connection, task, successors=[successor])
    assert len(list(iter_tasks(connection))) == 2
    next_task = claim_task(connection)
    assert next_task is not None
    assert next_task.task_id == successor.task_id


def test_bad_successor_rolls_back_completion(
    connection: sqlite3.Connection, source_file: Path
) -> None:
    spec = prepare_task(source_file, "inspect", "v1")
    enqueue_task(connection, spec)
    task = claim_task(connection)
    assert task is not None
    with pytest.raises(ValueError, match=ERROR_DEPENDENCIES_CHANGED):
        complete_task(connection, task, successors=[spec])
    assert get_task(connection, task.task_id).status == STATUS_RUNNING
    assert list(iter_attempts(connection, task.task_id))[0].finished_at is None


def test_dependencies_cannot_be_missing_or_changed(
    connection: sqlite3.Connection, source_file: Path
) -> None:
    spec = prepare_task(source_file, "rewrite", "v1")
    with pytest.raises(ValueError, match=ERROR_UNKNOWN_DEPENDENCY):
        enqueue_task(connection, spec, dependencies=["missing"])
    assert list(iter_tasks(connection)) == []
    first = enqueue_task(connection, prepare_task(source_file, "inspect", "v1"))
    enqueue_task(connection, spec, dependencies=[first.task_id])
    with pytest.raises(ValueError, match=ERROR_DEPENDENCIES_CHANGED):
        enqueue_task(connection, spec)


def test_failure_requires_explicit_retry_and_preserves_history(
    connection: sqlite3.Connection, source_file: Path
) -> None:
    spec = prepare_task(source_file, "inspect", "v1")
    enqueue_task(connection, spec)
    old = claim_task(connection)
    assert old is not None
    failed = fail_task(connection, old, ERROR_PROCESSING)
    assert failed.status == STATUS_FAILED
    assert enqueue_task(connection, spec) == failed
    assert claim_task(connection) is None
    retry_task(connection, old.task_id)
    current = claim_task(connection)
    assert current is not None
    assert current.attempt_count == 2
    assert current.attempt_token != old.attempt_token
    assert (
        list(iter_attempts(connection, old.task_id))[0].failure_code == ERROR_PROCESSING
    )
    with pytest.raises(ValueError, match=ERROR_STALE_ATTEMPT):
        complete_task(connection, old)
    with pytest.raises(ValueError, match=ERROR_STALE_ATTEMPT):
        fail_task(connection, old, ERROR_PROCESSING)


def test_failure_codes_cannot_contain_raw_exception_messages(
    connection: sqlite3.Connection, source_file: Path
) -> None:
    enqueue_task(connection, prepare_task(source_file, "inspect", "v1"))
    task = claim_task(connection)
    assert task is not None
    with pytest.raises(ValueError, match=ERROR_INVALID_FAILURE_CODE):
        fail_task(connection, task, "patient name appeared in parser exception")
    assert get_task(connection, task.task_id).status == STATUS_RUNNING


def test_invalid_retry_and_missing_task_fail_explicitly(
    connection: sqlite3.Connection, source_file: Path
) -> None:
    task = enqueue_task(connection, prepare_task(source_file, "inspect", "v1"))
    with pytest.raises(ValueError, match=ERROR_INVALID_TRANSITION):
        retry_task(connection, task.task_id)
    with pytest.raises(ValueError, match=ERROR_STALE_ATTEMPT):
        require_attempt(connection, task)
    with pytest.raises(KeyError, match=ERROR_TASK_NOT_FOUND):
        get_task(connection, "missing")


def test_recovery_is_explicit_and_preserves_completed_tasks(
    tmp_path: Path, source_file: Path
) -> None:
    state = tmp_path / STATE_DIRECTORY
    with closing(open_database(state)) as database:
        enqueue_task(database, prepare_task(source_file, "inspect", "v1"))
        claimed = claim_task(database)
        assert claimed is not None
        completed = complete_task(database, claimed)
        enqueue_task(database, prepare_task(source_file, "rewrite", "v1"))
        abandoned = claim_task(database)
        assert abandoned is not None

    with closing(open_database(state)) as database:
        assert get_task(database, abandoned.task_id).status == STATUS_RUNNING
        assert recover_interrupted(database) == 1
        assert recover_interrupted(database) == 0
        assert get_task(database, completed.task_id).status == STATUS_SUCCEEDED
        recovered = claim_task(database)
        assert recovered is not None
        assert recovered.task_id == abandoned.task_id
        assert recovered.attempt_token != abandoned.attempt_token
        attempts = list(iter_attempts(database, recovered.task_id))
        assert [attempt.status for attempt in attempts] == [
            STATUS_INTERRUPTED,
            STATUS_RUNNING,
        ]
        with pytest.raises(ValueError, match=ERROR_STALE_ATTEMPT):
            require_attempt(database, abandoned)


def test_queue_remains_available_after_reopen(
    tmp_path: Path, source_file: Path
) -> None:
    state = tmp_path / STATE_DIRECTORY
    with closing(open_database(state)) as database:
        task = enqueue_task(database, prepare_task(source_file, "inspect", "v1"))
    with closing(open_database(state)) as database:
        claimed = claim_task(database)
        assert claimed is not None
        assert claimed.task_id == task.task_id
        assert database.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
