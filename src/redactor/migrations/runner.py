"""Apply ordered SQL migrations within the caller's database transaction."""

import sqlite3
from collections.abc import Sequence
from importlib.resources.abc import Traversable

from redactor.utils.constants import TEXT_ENCODING
from redactor.utils.errors import (
    ERROR_INCOMPLETE_MIGRATION,
    ERROR_MIGRATION_TRANSACTION_REQUIRED,
    ERROR_UNSUPPORTED_SCHEMA,
)


def apply_migrations(
    connection: sqlite3.Connection, migration_files: Sequence[Traversable]
) -> None:
    """Apply pending migrations; the caller owns commit and rollback."""
    if not connection.in_transaction:
        raise RuntimeError(ERROR_MIGRATION_TRANSACTION_REQUIRED)

    # Recheck after acquiring the transaction: another opener may have migrated.
    version = connection.execute("PRAGMA user_version").fetchone()[0]
    if not 0 <= version <= len(migration_files):
        raise ValueError(ERROR_UNSUPPORTED_SCHEMA)

    for index in range(version, len(migration_files)):
        script = migration_files[index].read_text(encoding=TEXT_ENCODING)
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
