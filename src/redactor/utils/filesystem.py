"""Small filesystem primitives shared by database and artifact persistence."""

import os
from pathlib import Path

from redactor.utils.constants import PRIVATE_DIRECTORY_MODE


def sync_directory(directory: Path) -> None:
    """Persist directory entries after creating, renaming, or removing a file."""
    descriptor = os.open(directory, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def private_directory(directory: Path) -> None:
    """Create private directories and persist each newly created parent entry."""
    if not directory.exists():
        if not directory.parent.exists():
            private_directory(directory.parent)
        directory.mkdir(mode=PRIVATE_DIRECTORY_MODE, exist_ok=True)
        sync_directory(directory.parent)
    directory.chmod(PRIVATE_DIRECTORY_MODE)
