import hashlib
import os
import signal
import sqlite3
import subprocess
import sys
from contextlib import closing
from errno import EXDEV
from io import BytesIO
from pathlib import Path
from typing import BinaryIO

import pytest

from redactor.persistence.database import open_database, state_directory
from redactor.persistence.files import registration
from redactor.persistence.files.artifacts import (
    create_temporary_file,
    finalize_output,
    seal_temporary_file,
)
from redactor.persistence.files.hashing import hash_file, hash_stream
from redactor.persistence.files.registration import prepare_task, register_file
from redactor.persistence.queue.tasks import (
    claim_task,
    complete_task,
    enqueue_task,
    get_task,
    iter_tasks,
    recover_interrupted,
)
from redactor.schemas.persistence import Artifact, Task
from redactor.utils.constants import (
    OUTPUT_DIRECTORY,
    PRIVATE_DIRECTORY_MODE,
    PRIVATE_FILE_MODE,
    PUBLISHED_DIRECTORY,
    STATE_DIRECTORY,
    TEMPORARY_DIRECTORY,
)
from redactor.utils.errors import (
    ERROR_ARTIFACT_CORRUPT,
    ERROR_ARTIFACT_MISSING,
    ERROR_FILE_NOT_REGISTERED,
    ERROR_INPUT_CHANGED,
    ERROR_OUTPUT_CONFLICT,
    ERROR_OUTPUT_FILESYSTEM,
    ERROR_STALE_ATTEMPT,
    ERROR_TASK_ID_CONFLICT,
    ERROR_UNKNOWN_DEPENDENCY,
)


@pytest.fixture
def registered_task(connection: sqlite3.Connection, source_file: Path) -> Task:
    register_file(connection, source_file, "rewrite", "v1")
    task = claim_task(connection)
    assert task is not None
    return task


@pytest.fixture
def staged_artifact(connection: sqlite3.Connection, registered_task: Task) -> Artifact:
    temporary = create_temporary_file(connection, registered_task)
    temporary.write_bytes(b"completed synthetic output\n")
    return seal_temporary_file(connection, registered_task)


def test_registration_persists_input_and_locations_together(
    tmp_path: Path, source_file: Path
) -> None:
    state = tmp_path / STATE_DIRECTORY
    with closing(open_database(state)) as connection:
        task = register_file(connection, source_file, "inspect", "v1")

    with closing(open_database(state)) as connection:
        assert get_task(connection, task.task_id) == task
        assert register_file(connection, source_file, "inspect", "v1") == task
        assert list(iter_tasks(connection)) == [task]

    assert task.input_path == source_file.resolve()
    assert task.input_size == source_file.stat().st_size
    assert task.input_sha256 == hash_file(source_file)
    assert task.temporary_directory is not None
    assert task.output_path is not None
    assert task.temporary_directory == state / TEMPORARY_DIRECTORY / task.task_id
    assert task.output_path == (
        tmp_path / OUTPUT_DIRECTORY / PUBLISHED_DIRECTORY / source_file.name
    )
    assert not task.temporary_directory.exists()
    assert not task.output_path.exists()


def test_registration_preserves_completed_work(
    connection: sqlite3.Connection, source_file: Path
) -> None:
    register_file(connection, source_file, "inspect", "v1")
    claimed = claim_task(connection)
    assert claimed is not None
    completed = complete_task(connection, claimed)
    assert register_file(connection, source_file, "inspect", "v1") == completed
    assert claim_task(connection) is None


def test_registration_adds_locations_to_an_existing_task(
    connection: sqlite3.Connection, source_file: Path
) -> None:
    spec = prepare_task(source_file, "inspect", "v1")
    original = enqueue_task(connection, spec)
    registered = register_file(connection, source_file, "inspect", "v1")
    assert registered.task_id == original.task_id
    assert registered.temporary_directory is not None
    assert registered.output_path is not None
    assert enqueue_task(connection, spec) == registered


def test_registered_locations_cannot_be_replaced(
    connection: sqlite3.Connection, source_file: Path
) -> None:
    task = register_file(connection, source_file, "inspect", "v1")
    spec = prepare_task(source_file, "inspect", "v1")
    changed = spec.model_copy(update={"output_path": source_file})
    with pytest.raises(ValueError, match=ERROR_TASK_ID_CONFLICT):
        enqueue_task(connection, changed)
    assert get_task(connection, task.task_id) == task


def test_registration_tracks_each_step_separately(
    connection: sqlite3.Connection, source_file: Path
) -> None:
    first = register_file(connection, source_file, "inspect", "v1")
    second = register_file(
        connection, source_file, "rewrite", "v1", dependencies=[first.task_id]
    )
    assert second.task_id != first.task_id
    assert second.temporary_directory != first.temporary_directory
    assert claim_task(connection) is not None
    assert claim_task(connection) is None


def test_failed_registration_does_not_leave_partial_state(
    connection: sqlite3.Connection, source_file: Path
) -> None:
    with pytest.raises(ValueError, match=ERROR_UNKNOWN_DEPENDENCY):
        register_file(
            connection, source_file, "inspect", "v1", dependencies=["missing"]
        )
    assert list(iter_tasks(connection)) == []
    assert not (state_directory(connection) / TEMPORARY_DIRECTORY).exists()


def test_input_changes_during_registration_are_rejected(
    connection: sqlite3.Connection, source_file: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def change_input(stream: BinaryIO, length: int | None = None) -> str:
        digest = hash_stream(stream, length)
        source_file.write_bytes(b"changed after hashing")
        return digest

    monkeypatch.setattr(registration, "hash_stream", change_input)
    with pytest.raises(ValueError, match=ERROR_INPUT_CHANGED):
        register_file(connection, source_file, "inspect", "v1")
    assert list(iter_tasks(connection)) == []


def test_binary_hashing_preserves_bytes_and_stream_position() -> None:
    payload = bytes(range(256)) * 8193
    stream = BytesIO(payload)
    stream.seek(3)
    assert hash_stream(stream, 111) == hashlib.sha256(payload[3:114]).hexdigest()
    assert stream.tell() == 114
    assert hash_stream(stream) == hashlib.sha256(payload[114:]).hexdigest()


def test_temporary_creation_is_private_and_does_not_truncate(
    connection: sqlite3.Connection, registered_task: Task
) -> None:
    temporary = create_temporary_file(connection, registered_task)
    temporary.write_bytes(b"partial progress")
    assert create_temporary_file(connection, registered_task) == temporary
    assert temporary.read_bytes() == b"partial progress"
    assert temporary.stat().st_mode & 0o777 == PRIVATE_FILE_MODE
    assert temporary.parent.stat().st_mode & 0o777 == PRIVATE_DIRECTORY_MODE
    assert registered_task.output_path is not None
    assert not registered_task.output_path.exists()


def test_new_attempt_uses_a_different_temporary_file(
    connection: sqlite3.Connection, registered_task: Task
) -> None:
    original = create_temporary_file(connection, registered_task)
    original.write_bytes(b"old attempt")
    recover_interrupted(connection)
    current = claim_task(connection)
    assert current is not None
    replacement = create_temporary_file(connection, current)
    assert replacement != original
    assert replacement.read_bytes() == b""
    assert original.read_bytes() == b"old attempt"
    with pytest.raises(ValueError, match=ERROR_STALE_ATTEMPT):
        create_temporary_file(connection, registered_task)


def test_artifact_helpers_require_registered_file_locations(
    connection: sqlite3.Connection, source_file: Path
) -> None:
    enqueue_task(connection, prepare_task(source_file, "inspect", "v1"))
    task = claim_task(connection)
    assert task is not None
    with pytest.raises(ValueError, match=ERROR_FILE_NOT_REGISTERED):
        create_temporary_file(connection, task)


def test_sealing_requires_an_existing_temporary_file(
    connection: sqlite3.Connection, registered_task: Task
) -> None:
    with pytest.raises(ValueError, match=ERROR_ARTIFACT_MISSING):
        seal_temporary_file(connection, registered_task)


def test_output_finalization_is_repeatable_and_leaves_input_untouched(
    connection: sqlite3.Connection,
    registered_task: Task,
    staged_artifact: Artifact,
) -> None:
    original = registered_task.input_path.read_bytes()
    output = finalize_output(connection, registered_task, staged_artifact)
    assert output.path == registered_task.output_path
    assert output.path.read_bytes() == b"completed synthetic output\n"
    assert output.sha256 == staged_artifact.sha256
    assert output.size == staged_artifact.size
    assert not staged_artifact.path.exists()
    assert finalize_output(connection, registered_task, staged_artifact) == output
    assert registered_task.input_path.read_bytes() == original
    assert get_task(connection, registered_task.task_id) == registered_task


def test_changed_bytes_cannot_be_published_after_verification(
    connection: sqlite3.Connection, registered_task: Task, staged_artifact: Artifact
) -> None:
    staged_artifact.path.write_bytes(b"changed after verification")
    with pytest.raises(ValueError, match=ERROR_ARTIFACT_CORRUPT):
        finalize_output(connection, registered_task, staged_artifact)
    assert registered_task.output_path is not None
    assert not registered_task.output_path.exists()


def test_conflicting_output_is_preserved(
    connection: sqlite3.Connection, registered_task: Task, staged_artifact: Artifact
) -> None:
    output_path = registered_task.output_path
    assert output_path is not None
    output_path.parent.mkdir(parents=True)
    output_path.write_bytes(b"existing different output")
    with pytest.raises(ValueError, match=ERROR_OUTPUT_CONFLICT):
        finalize_output(connection, registered_task, staged_artifact)
    assert output_path.read_bytes() == b"existing different output"
    assert staged_artifact.path.exists()


def test_existing_identical_output_allows_cleanup_and_retry(
    connection: sqlite3.Connection, registered_task: Task, staged_artifact: Artifact
) -> None:
    output_path = registered_task.output_path
    assert output_path is not None
    output_path.parent.mkdir(parents=True)
    output_path.write_bytes(staged_artifact.path.read_bytes())
    assert (
        finalize_output(connection, registered_task, staged_artifact).path
        == output_path
    )
    assert not staged_artifact.path.exists()


def test_stale_attempt_cannot_seal_or_publish(
    connection: sqlite3.Connection, registered_task: Task, staged_artifact: Artifact
) -> None:
    recover_interrupted(connection)
    with pytest.raises(ValueError, match=ERROR_STALE_ATTEMPT):
        seal_temporary_file(connection, registered_task)
    with pytest.raises(ValueError, match=ERROR_STALE_ATTEMPT):
        finalize_output(connection, registered_task, staged_artifact)


def test_artifact_path_must_belong_to_this_attempt(
    connection: sqlite3.Connection, registered_task: Task, staged_artifact: Artifact
) -> None:
    wrong_path = staged_artifact.model_copy(update={"path": registered_task.input_path})
    with pytest.raises(ValueError, match=ERROR_ARTIFACT_CORRUPT):
        finalize_output(connection, registered_task, wrong_path)


def test_cross_filesystem_finalization_fails_without_a_partial_output(
    connection: sqlite3.Connection,
    registered_task: Task,
    staged_artifact: Artifact,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def cross_device_link(source: Path, target: Path, *, follow_symlinks: bool) -> None:
        raise OSError(EXDEV, "cross-device link")

    monkeypatch.setattr(os, "link", cross_device_link)
    with pytest.raises(ValueError, match=ERROR_OUTPUT_FILESYSTEM):
        finalize_output(connection, registered_task, staged_artifact)
    assert registered_task.output_path is not None
    assert not registered_task.output_path.exists()
    assert staged_artifact.path.exists()


def test_symlinks_cannot_substitute_for_staged_bytes(
    connection: sqlite3.Connection, registered_task: Task, staged_artifact: Artifact
) -> None:
    staged_artifact.path.unlink()
    staged_artifact.path.symlink_to(registered_task.input_path)
    with pytest.raises(ValueError, match=ERROR_ARTIFACT_CORRUPT):
        seal_temporary_file(connection, registered_task)


@pytest.mark.parametrize("crash_point", ["before_link", "after_link", "after_cleanup"])
def test_finalization_can_be_replayed_after_sigkill(
    tmp_path: Path, source_file: Path, crash_point: str
) -> None:
    state = tmp_path / STATE_DIRECTORY
    with closing(open_database(state)) as connection:
        register_file(connection, source_file, "rewrite", "v1")
        claimed = claim_task(connection)
        assert claimed is not None
        temporary = create_temporary_file(connection, claimed)
        temporary.write_bytes(b"complete output only\n")
        verified = seal_temporary_file(connection, claimed)

    helper = Path(__file__).parent / "support" / "crash_during_finalize.py"
    process = subprocess.run(
        [sys.executable, str(helper), str(state), claimed.task_id, crash_point],
        capture_output=True,
        timeout=10,
        check=False,
    )
    assert process.returncode == -signal.SIGKILL, process.stderr.decode()
    assert claimed.output_path is not None
    if crash_point == "before_link":
        assert not claimed.output_path.exists()
    else:
        assert claimed.output_path.read_bytes() == b"complete output only\n"

    with closing(open_database(state)) as connection:
        output = finalize_output(connection, claimed, verified)
        completed = complete_task(connection, claimed, result=output)
        assert register_file(connection, source_file, "rewrite", "v1") == completed
        assert claim_task(connection) is None
        assert output.path.read_bytes() == b"complete output only\n"
        assert not temporary.exists()
