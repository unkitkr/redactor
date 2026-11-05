"""Hold exclusive run ownership until the coordinator and every worker exit."""

import fcntl
import os
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

from redactor.utils.constants import PRIVATE_FILE_MODE, RUN_LOCK_FILENAME
from redactor.utils.errors import ERROR_RUN_ACTIVE
from redactor.utils.filesystem import private_directory


@contextmanager
def own_run(state_directory: Path) -> Generator[int, None, None]:
    """Yield the descriptor that workers must inherit for their whole lifetime.

    Never unlink this file or use LOCK_UN: inherited descriptors share this lock,
    and closing our copy must not release ownership held by a surviving worker.
    """
    private_directory(state_directory)
    descriptor = os.open(
        state_directory / RUN_LOCK_FILENAME,
        os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW,
        PRIVATE_FILE_MODE,
    )
    try:
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise RuntimeError(ERROR_RUN_ACTIVE) from error
        os.fchmod(descriptor, PRIVATE_FILE_MODE)
        yield descriptor
    finally:
        os.close(descriptor)
