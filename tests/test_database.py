import sqlite3
from contextlib import closing

import pytest

from redactor.persistence.database import open_database, state_directory, transaction
from redactor.utils.constants import (
    DATABASE_FILENAME,
    ERROR_NESTED_TRANSACTION,
    ERROR_UNSUPPORTED_SCHEMA,
    PRIVATE_DIRECTORY_MODE,
    PRIVATE_FILE_MODE,
    STATE_DIRECTORY,
)


def test_state_is_private_and_uses_durable_settings(connection):
    directory = state_directory(connection)
    assert directory.stat().st_mode & 0o777 == PRIVATE_DIRECTORY_MODE
    assert (directory / DATABASE_FILENAME).stat().st_mode & 0o777 == PRIVATE_FILE_MODE
    assert connection.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
    assert connection.execute("PRAGMA synchronous").fetchone()[0] == 2
    assert connection.execute("PRAGMA foreign_keys").fetchone()[0] == 1


def test_transactions_rollback_on_base_exception(connection):
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


def test_transactions_do_not_nest(connection):
    with transaction(connection):
        with pytest.raises(RuntimeError, match=ERROR_NESTED_TRANSACTION):
            with transaction(connection):
                pytest.fail("Nested transaction succeeded")


def test_future_schema_is_rejected_without_rewriting_it(tmp_path):
    state = tmp_path / STATE_DIRECTORY
    with closing(open_database(state)) as connection:
        connection.execute("PRAGMA user_version = 999")
    with pytest.raises(ValueError, match=ERROR_UNSUPPORTED_SCHEMA):
        with closing(open_database(state)):
            pytest.fail("Unknown schema was accepted")
    with closing(sqlite3.connect(state / DATABASE_FILENAME)) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 999
