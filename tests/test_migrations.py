import sqlite3
from contextlib import closing
from pathlib import Path

import pytest

from redactor import migrations
from redactor.migrations import discover_migrations
from redactor.migrations.runner import apply_migrations
from redactor.persistence.database import open_database
from redactor.persistence.files.registration import prepare_task
from redactor.persistence.queue.tasks import enqueue_task, get_task
from redactor.utils.constants import STATE_DIRECTORY
from redactor.utils.errors import (
    ERROR_INVALID_MIGRATIONS,
    ERROR_MIGRATION_TRANSACTION_REQUIRED,
)


@pytest.fixture
def migration_directory(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    directory = tmp_path / "migrations"
    directory.mkdir()

    def resource_directory(package: str) -> Path:
        return directory

    monkeypatch.setattr(migrations, "files", resource_directory)
    return directory


def test_discovery_sorts_versions_numerically_and_ignores_other_files(
    migration_directory: Path,
) -> None:
    for version in reversed(range(1, 11)):
        (migration_directory / f"{version}_step.sql").write_text("SELECT 1;\n")
    (migration_directory / "README.md").write_text("Migration notes")
    (migration_directory / "constants.py").write_text("")
    (migration_directory / "011_directory.sql").mkdir()

    assert [migration.name for migration in discover_migrations()] == [
        f"{version}_step.sql" for version in range(1, 11)
    ]


@pytest.mark.parametrize(
    "names",
    [
        (),
        ("001_first.sql", "003_gap.sql"),
        ("001_first.sql", "1_duplicate.sql"),
        ("000_zero.sql",),
        ("initial.sql",),
        ("001_.sql",),
    ],
)
def test_invalid_migration_sequences_are_rejected(
    migration_directory: Path, names: tuple[str, ...]
) -> None:
    for name in names:
        (migration_directory / name).write_text("SELECT 1;\n")
    with pytest.raises(ValueError, match=ERROR_INVALID_MIGRATIONS):
        discover_migrations()


def test_migrations_require_an_explicit_transaction(
    connection: sqlite3.Connection,
) -> None:
    with pytest.raises(RuntimeError, match=ERROR_MIGRATION_TRANSACTION_REQUIRED):
        apply_migrations(connection, discover_migrations())


def test_adding_sql_file_advances_schema_without_a_registry_change(
    tmp_path: Path, source_file: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    directory = tmp_path / "migrations"
    directory.mkdir()
    for source in discover_migrations():
        (directory / source.name).write_text(source.read_text())

    def resource_directory(package: str) -> Path:
        return directory

    monkeypatch.setattr(migrations, "files", resource_directory)
    state = tmp_path / STATE_DIRECTORY
    with closing(open_database(state)) as connection:
        task = enqueue_task(connection, prepare_task(source_file, "inspect", "v1"))
        previous_version = connection.execute("PRAGMA user_version").fetchone()[0]

    (directory / f"{previous_version + 1:03d}_marker.sql").write_text(
        "CREATE TABLE marker (value INTEGER);\nINSERT INTO marker VALUES (42);\n"
    )
    with closing(open_database(state)) as connection:
        assert get_task(connection, task.task_id) == task
        assert connection.execute("SELECT value FROM marker").fetchone()[0] == 42
        assert connection.execute("PRAGMA user_version").fetchone()[0] == (
            previous_version + 1
        )

    # Reopening must not try to apply the same CREATE TABLE again.
    with closing(open_database(state)) as connection:
        assert connection.execute("SELECT count(*) FROM marker").fetchone()[0] == 1
        assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
