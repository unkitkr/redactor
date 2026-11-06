"""Hashing helpers for durable file processing."""

import hashlib
import os
from pathlib import Path
from typing import BinaryIO

from redactor.utils.constants import HASH_CHUNK_BYTES, READ_BINARY
from redactor.utils.errors import ERROR_ARTIFACT_CORRUPT


def file_version(metadata: os.stat_result) -> tuple[int, int, int, int, int]:
    """Compare identity and modification metadata without access-time changes."""
    return (
        metadata.st_dev,
        metadata.st_ino,
        metadata.st_size,
        metadata.st_mtime_ns,
        metadata.st_ctime_ns,
    )


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
