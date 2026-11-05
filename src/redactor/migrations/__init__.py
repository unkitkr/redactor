"""Ordered SQL migrations, packaged with the application and never edited in place."""

import re
from importlib.resources import files
from importlib.resources.abc import Traversable

from redactor.migrations.constants import MIGRATION_FILENAME_PATTERN, SQL_SUFFIX
from redactor.utils.errors import ERROR_INVALID_MIGRATIONS


def discover_migrations() -> tuple[Traversable, ...]:
    """Discover SQL files in version order; their count is the schema version.

    Versions must start at one and have no duplicates or gaps. Discovery happens
    when called, so importing this package performs no filesystem I/O.
    """
    numbered = []
    for entry in files(__name__).iterdir():
        if not entry.is_file() or not entry.name.endswith(SQL_SUFFIX):
            continue
        match = re.fullmatch(MIGRATION_FILENAME_PATTERN, entry.name)
        if match is None:
            raise ValueError(ERROR_INVALID_MIGRATIONS)
        numbered.append((int(match.group(1)), entry))

    numbered.sort(key=lambda item: item[0])
    versions = [version for version, _ in numbered]
    if not versions or versions != list(range(1, len(numbered) + 1)):
        raise ValueError(ERROR_INVALID_MIGRATIONS)
    return tuple(entry for _, entry in numbered)
