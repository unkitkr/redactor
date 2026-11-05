"""SQLite setup and explicit, short transactions on a local state directory."""

import sqlite3
from collections.abc import Generator
from contextlib import contextmanager
from importlib.resources import files
from pathlib import Path

from redactor.utils.constants import (
    DATABASE_FILENAME,
    MIGRATION_FILENAMES,
    MIGRATIONS_PACKAGE,
    PRIVATE_FILE_MODE,
    SCHEMA_VERSION,
    SQLITE_CACHE_KIB,
    SQLITE_JOURNAL_MODE,
    SQLITE_SYNCHRONOUS,
    SQLITE_TEMP_STORE,
    SQLITE_TIMEOUT_SECONDS,
    TEXT_ENCODING,
    TRANSACTION_BEGIN,
    TRANSACTION_COMMIT,
    TRANSACTION_ROLLBACK,
)
from redactor.utils.errors import (
    ERROR_INCOMPLETE_MIGRATION,
    ERROR_NESTED_TRANSACTION,
    ERROR_UNSUPPORTED_SCHEMA,
    ERROR_WAL_UNAVAILABLE,
)
from redactor.utils.filesystem import private_directory, sync_directory


@contextmanager
def transaction(connection: sqlite3.Connection) -> Generator[None, None, None]:
    """Roll back even on interruption; never accidentally nest transactions."""
    if connection.in_transaction:
        raise RuntimeError(ERROR_NESTED_TRANSACTION)

    connection.execute(TRANSACTION_BEGIN)
    try:
        yield
        connection.execute(TRANSACTION_COMMIT)
    except BaseException:
        if connection.in_transaction:
            connection.execute(TRANSACTION_ROLLBACK)
        raise


def open_database(state_directory: Path) -> sqlite3.Connection:
    """Open durable state without claiming, scheduling, or recovering any work.

    Each process/thread owns its connection. The caller must close it explicitly.
    Runtime ownership and worker lifecycle will be implemented separately.
    """
    state_directory = state_directory.resolve()
    private_directory(state_directory)
    database_path = state_directory / DATABASE_FILENAME
    connection = sqlite3.connect(
        database_path,
        timeout=SQLITE_TIMEOUT_SECONDS,
        isolation_level=None,
    )
    connection.row_factory = sqlite3.Row

    try:
        database_path.chmod(PRIVATE_FILE_MODE)
        version = connection.execute("PRAGMA user_version").fetchone()[0]
        if not 0 <= version <= SCHEMA_VERSION:
            raise ValueError(ERROR_UNSUPPORTED_SCHEMA)

        mode = connection.execute(
            f"PRAGMA journal_mode = {SQLITE_JOURNAL_MODE}"
        ).fetchone()[0]
        if mode != SQLITE_JOURNAL_MODE:
            raise RuntimeError(ERROR_WAL_UNAVAILABLE)

        connection.execute(f"PRAGMA synchronous = {SQLITE_SYNCHRONOUS}")
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute(f"PRAGMA cache_size = {-SQLITE_CACHE_KIB}")
        connection.execute(f"PRAGMA temp_store = {SQLITE_TEMP_STORE}")

        if version != SCHEMA_VERSION:
            _initialize_schema(connection)
        sync_directory(state_directory)
    except BaseException:
        connection.close()
        raise

    return connection


def state_directory(connection: sqlite3.Connection) -> Path:
    return Path(connection.execute("PRAGMA database_list").fetchone()[2]).parent


def _initialize_schema(connection: sqlite3.Connection) -> None:
    """Apply pending migrations and advance the schema version atomically."""
    with transaction(connection):
        version = connection.execute("PRAGMA user_version").fetchone()[0]
        if not 0 <= version <= SCHEMA_VERSION:
            raise ValueError(ERROR_UNSUPPORTED_SCHEMA)

        directory = files(MIGRATIONS_PACKAGE)
        for index in range(version, SCHEMA_VERSION):
            script = directory.joinpath(MIGRATION_FILENAMES[index]).read_text(
                encoding=TEXT_ENCODING
            )
            _execute_migration(connection, script)
            connection.execute(f"PRAGMA user_version = {index + 1}")


def _execute_migration(connection: sqlite3.Connection, script: str) -> None:
    """Execute complete statements without executescript's implicit commit."""
    statement = ""
    for line in script.splitlines(keepends=True):
        statement += line
        if sqlite3.complete_statement(statement):
            connection.execute(statement)
            statement = ""
    if statement.strip():
        raise ValueError(ERROR_INCOMPLETE_MIGRATION)
