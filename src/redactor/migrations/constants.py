"""Naming rules for migration files owned by this package."""

from typing import Final

SQL_SUFFIX: Final = ".sql"
MIGRATION_FILENAME_PATTERN: Final = r"([0-9]+)_.+\.sql"
