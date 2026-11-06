import sqlite3
from contextlib import closing
from pathlib import Path

import pytest

from redactor import migrations
from redactor.migrations import discover_migrations
from redactor.persistence.database import open_database, state_directory, transaction
from redactor.persistence.files import prepare_task
from redactor.persistence.queue import get_task
from redactor.utils.constants import (
    DATABASE_FILENAME,
    PRIVATE_DIRECTORY_MODE,
    PRIVATE_FILE_MODE,
    STATE_DIRECTORY,
)
from redactor.utils.errors import (
    ERROR_NESTED_TRANSACTION,
    ERROR_UNSUPPORTED_SCHEMA,
)


def test_state_is_private_and_uses_durable_settings(
    connection: sqlite3.Connection,
) -> None:
    directory = state_directory(connection)
    assert directory.stat().st_mode & 0o777 == PRIVATE_DIRECTORY_MODE
    assert (directory / DATABASE_FILENAME).stat().st_mode & 0o777 == PRIVATE_FILE_MODE
    assert connection.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
    assert connection.execute("PRAGMA synchronous").fetchone()[0] == 2
    assert connection.execute("PRAGMA foreign_keys").fetchone()[0] == 1


def test_transactions_rollback_on_base_exception(
    connection: sqlite3.Connection,
) -> None:
    with pytest.raises(KeyboardInterrupt):
        with transaction(connection):
            connection.execute("CREATE TABLE interrupted (value INTEGER)")
            raise KeyboardInterrupt
    assert not connection.in_transaction
    assert (
        connection.execute(
            "SELECT name FROM sqlite_master WHERE name = 'interrupted'"
        ).fetchone()
        is None
    )


def test_transactions_do_not_nest(connection: sqlite3.Connection) -> None:
    with transaction(connection):
        with pytest.raises(RuntimeError, match=ERROR_NESTED_TRANSACTION):
            with transaction(connection):
                pytest.fail("Nested transaction succeeded")


def test_future_schema_is_rejected_without_rewriting_it(tmp_path: Path) -> None:
    state = tmp_path / STATE_DIRECTORY
    with closing(open_database(state)) as connection:
        connection.execute("PRAGMA user_version = 999")
    with pytest.raises(ValueError, match=ERROR_UNSUPPORTED_SCHEMA):
        with closing(open_database(state)):
            pytest.fail("Unknown schema was accepted")
    with closing(sqlite3.connect(state / DATABASE_FILENAME)) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 999


def test_previous_schema_is_migrated_without_losing_tasks(
    tmp_path: Path, source_file: Path
) -> None:
    state = tmp_path / STATE_DIRECTORY
    create_initial_database(state)
    with closing(sqlite3.connect(state / DATABASE_FILENAME)) as connection:
        connection.row_factory = sqlite3.Row
        spec = prepare_task(source_file, "inspect", "v1")
        connection.execute(
            """
            INSERT INTO tasks (
                task_id, input_path, input_sha256, input_size, step,
                processing_version, status, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, 'pending', 'initial', 'initial')
            """,
            (
                spec.task_id,
                str(spec.input_path),
                spec.input_sha256,
                spec.input_size,
                spec.step,
                spec.processing_version,
            ),
        )
        connection.commit()
        task = get_task(connection, spec.task_id)

    with closing(open_database(state)) as connection:
        assert get_task(connection, task.task_id) == task
        assert connection.execute("PRAGMA user_version").fetchone()[0] == len(
            discover_migrations()
        )


def test_failed_migration_rolls_back_schema_and_version(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    state = tmp_path / STATE_DIRECTORY
    create_initial_database(state)

    for source in discover_migrations():
        (tmp_path / source.name).write_text(source.read_text())
    migration = tmp_path / "002_file_locations.sql"
    migration.write_text(
        "ALTER TABLE tasks ADD COLUMN temporary_directory TEXT;\n"
        "INSERT INTO missing_table VALUES (1);\n"
    )

    def migration_directory(package: str) -> Path:
        return tmp_path

    monkeypatch.setattr(migrations, "files", migration_directory)
    with pytest.raises(sqlite3.OperationalError):
        with closing(open_database(state)):
            pytest.fail("Invalid migration succeeded")

    with closing(sqlite3.connect(state / DATABASE_FILENAME)) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 1
        columns = {
            row[1] for row in connection.execute("PRAGMA table_info(tasks)").fetchall()
        }
        assert "temporary_directory" not in columns
        assert "output_path" not in columns


def create_initial_database(state: Path) -> None:
    """Build the historical schema rather than relabeling a newer database."""
    state.mkdir()
    with closing(sqlite3.connect(state / DATABASE_FILENAME)) as connection:
        connection.executescript(discover_migrations()[0].read_text())
        connection.execute("PRAGMA user_version = 1")
