"""Small, bounded-memory filesystem operations shared by persistence code."""

import hashlib
import os
from pathlib import Path
from typing import BinaryIO

from redactor.utils.constants import (
    ERROR_ARTIFACT_CORRUPT,
    HASH_CHUNK_BYTES,
    PRIVATE_DIRECTORY_MODE,
    READ_BINARY,
)


def sync_directory(directory: Path) -> None:
    """Persist directory entries after creating or renaming a durable artifact."""
    descriptor = os.open(directory, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def private_directory(directory: Path) -> None:
    directory.mkdir(parents=True, exist_ok=True, mode=PRIVATE_DIRECTORY_MODE)
    directory.chmod(PRIVATE_DIRECTORY_MODE)
    sync_directory(directory.parent)


def hash_file(file_path: Path) -> str:
    with file_path.open(READ_BINARY) as stream:
        return hash_stream(stream)


def hash_stream(stream: BinaryIO, length: int | None = None) -> str:
    """Hash from the current position without materializing the file in memory."""
    digest = hashlib.sha256()
    remaining = length

    while remaining is None or remaining > 0:
        chunk_size = (
            HASH_CHUNK_BYTES if remaining is None else min(HASH_CHUNK_BYTES, remaining)
        )
        chunk = stream.read(chunk_size)
        if not chunk:
            if remaining:
                raise ValueError(ERROR_ARTIFACT_CORRUPT)
            break

        digest.update(chunk)
        if remaining is not None:
            remaining -= len(chunk)

    return digest.hexdigest()
