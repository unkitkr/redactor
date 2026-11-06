"""Read a bounded regular file without following its final symlink."""

import os
import stat
from pathlib import Path


def read_bounded_file(path: Path, maximum: int) -> bytes:
    """The caller separately constrains and validates the parent directory."""
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(descriptor, "rb") as stream:
        details = os.fstat(stream.fileno())
        if not stat.S_ISREG(details.st_mode) or details.st_size > maximum:
            raise ValueError("Invalid file")
        payload = stream.read(maximum + 1)
    if len(payload) > maximum:
        raise ValueError("Oversized file")
    return payload
