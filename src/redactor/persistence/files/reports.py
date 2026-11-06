"""Atomically replace derived reports; the execution ledger remains authoritative."""

import os
import tempfile
from pathlib import Path

from redactor.utils.errors import ERROR_OUTPUT_CONFLICT
from redactor.utils.filesystem import private_directory, sync_directory


def replace_report(destination: Path, payload: bytes) -> None:
    private_directory(destination.parent)
    if destination.is_symlink():
        raise ValueError(ERROR_OUTPUT_CONFLICT)
    descriptor, name = tempfile.mkstemp(dir=destination.parent)
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, destination)
        sync_directory(destination.parent)
    finally:
        temporary.unlink(missing_ok=True)
