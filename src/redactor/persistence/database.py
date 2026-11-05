"""SQLite setup and explicit, short transactions on a local state directory."""

import sqlite3
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

from redactor.migrations import discover_migrations
from redactor.migrations.runner import apply_migrations
from redactor.utils.constants import (
    DATABASE_FILENAME,
    PRIVATE_FILE_MODE,
    SQLITE_CACHE_KIB,
    SQLITE_JOURNAL_MODE,
    SQLITE_SYNCHRONOUS,
    SQLITE_TEMP_STORE,
    SQLITE_TIMEOUT_SECONDS,
    TRANSACTION_BEGIN,
    TRANSACTION_COMMIT,
    TRANSACTION_ROLLBACK,
)
from redactor.utils.errors import (
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
    Runtime ownership and worker lifecycle belong to the coordinator package.
    """
    migration_files = discover_migrations()
    latest_version = len(migration_files)
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
        if not 0 <= version <= latest_version:
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

        if version != latest_version:
            with transaction(connection):
                apply_migrations(connection, migration_files)
        sync_directory(state_directory)
    except BaseException:
        connection.close()
        raise

    return connection


def state_directory(connection: sqlite3.Connection) -> Path:
    return Path(connection.execute("PRAGMA database_list").fetchone()[2]).parent
