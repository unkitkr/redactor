import hashlib
import sqlite3
from contextlib import closing
from io import BytesIO
from pathlib import Path
from typing import BinaryIO

import pytest

from redactor.persistence import files
from redactor.persistence.database import open_database, state_directory
from redactor.persistence.files import (
    hash_file,
    hash_stream,
    prepare_task,
    register_file,
)
from redactor.persistence.queue import (
    claim_task,
    complete_task,
    enqueue_task,
    get_task,
    iter_tasks,
)
from redactor.utils.constants import (
    ERROR_INPUT_CHANGED,
    ERROR_TASK_ID_CONFLICT,
    ERROR_UNKNOWN_DEPENDENCY,
    OUTPUT_DIRECTORY,
    PUBLISHED_DIRECTORY,
    STATE_DIRECTORY,
    TEMPORARY_DIRECTORY,
)


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

    monkeypatch.setattr(files, "hash_stream", change_input)
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
