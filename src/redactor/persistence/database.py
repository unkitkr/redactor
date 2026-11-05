"""SQLite setup and explicit, short transactions on a local state directory."""

import sqlite3
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

from redactor.persistence.files import private_directory, sync_directory
from redactor.utils.constants import (
    DATABASE_FILENAME,
    ERROR_NESTED_TRANSACTION,
    ERROR_UNSUPPORTED_SCHEMA,
    ERROR_WAL_UNAVAILABLE,
    PRIVATE_FILE_MODE,
    SCHEMA_VERSION,
    SQLITE_CACHE_KIB,
    SQLITE_JOURNAL_MODE,
    SQLITE_SYNCHRONOUS,
    SQLITE_TEMP_STORE,
    SQLITE_TIMEOUT_SECONDS,
    STATUS_FAILED,
    STATUS_INTERRUPTED,
    STATUS_PENDING,
    STATUS_RUNNING,
    STATUS_SUCCEEDED,
    TRANSACTION_BEGIN,
    TRANSACTION_COMMIT,
    TRANSACTION_ROLLBACK,
)


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
        if version not in (0, SCHEMA_VERSION):
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

        if version == 0:
            _create_schema(connection)
        sync_directory(state_directory)
    except BaseException:
        connection.close()
        raise

    return connection


def state_directory(connection: sqlite3.Connection) -> Path:
    return Path(connection.execute("PRAGMA database_list").fetchone()[2]).parent


def _create_schema(connection: sqlite3.Connection) -> None:
    """Schema creation and its version marker commit together."""
    with transaction(connection):
        version = connection.execute("PRAGMA user_version").fetchone()[0]
        if version == SCHEMA_VERSION:
            return
        if version != 0:
            raise ValueError(ERROR_UNSUPPORTED_SCHEMA)

        connection.execute(
            f"""
            CREATE TABLE tasks (
                task_id TEXT PRIMARY KEY,
                input_path TEXT NOT NULL,
                input_sha256 TEXT NOT NULL,
                input_size INTEGER NOT NULL CHECK (input_size >= 0),
                step TEXT NOT NULL,
                processing_version TEXT NOT NULL,
                status TEXT NOT NULL CHECK (status IN (
                    '{STATUS_PENDING}', '{STATUS_RUNNING}',
                    '{STATUS_SUCCEEDED}', '{STATUS_FAILED}'
                )),
                attempt_token TEXT,
                attempt_count INTEGER NOT NULL DEFAULT 0,
                failure_code TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                result_path TEXT,
                result_sha256 TEXT,
                result_size INTEGER CHECK (result_size >= 0)
            )
            """
        )
        connection.execute(
            """
            CREATE INDEX tasks_ready ON tasks (status, created_at, task_id)
            """
        )
        connection.execute(
            """
            CREATE TABLE dependencies (
                task_id TEXT NOT NULL REFERENCES tasks(task_id),
                depends_on TEXT NOT NULL REFERENCES tasks(task_id),
                PRIMARY KEY (task_id, depends_on),
                CHECK (task_id != depends_on)
            )
            """
        )
        connection.execute(
            f"""
            CREATE TABLE attempts (
                task_id TEXT NOT NULL REFERENCES tasks(task_id),
                attempt_token TEXT PRIMARY KEY,
                status TEXT NOT NULL CHECK (status IN (
                    '{STATUS_RUNNING}', '{STATUS_SUCCEEDED}',
                    '{STATUS_FAILED}', '{STATUS_INTERRUPTED}'
                )),
                started_at TEXT NOT NULL,
                finished_at TEXT,
                failure_code TEXT
            )
            """
        )
        connection.execute(
            """
            CREATE INDEX attempts_by_task ON attempts (task_id, started_at)
            """
        )
        connection.execute(
            """
            CREATE TABLE checkpoints (
                task_id TEXT NOT NULL REFERENCES tasks(task_id),
                sequence INTEGER NOT NULL CHECK (sequence > 0),
                artifact_path TEXT NOT NULL,
                input_offset INTEGER NOT NULL CHECK (input_offset >= 0),
                output_offset INTEGER NOT NULL CHECK (output_offset >= 0),
                record_count INTEGER NOT NULL CHECK (record_count >= 0),
                output_prefix_sha256 TEXT NOT NULL,
                counts_json TEXT NOT NULL,
                PRIMARY KEY (task_id, sequence)
            )
            """
        )
        connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
