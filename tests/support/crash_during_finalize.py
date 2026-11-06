"""Isolated SIGKILL injection at artifact publication boundaries."""

import os
import signal
import sys
from collections.abc import Sequence
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from redactor.persistence.database import open_database
from redactor.persistence.files import artifacts
from redactor.persistence.queue.tasks import get_task
from redactor.utils.filesystem import sync_directory


def main(arguments: Sequence[str]) -> None:
    state_path, task_id, crash_point = arguments
    original_link = os.link
    original_sync = sync_directory

    with closing(open_database(Path(state_path))) as connection:
        task = get_task(connection, task_id)
        artifact = artifacts.seal_temporary_file(connection, task)

        def interrupted_link(
            source: Path, target: Path, *, follow_symlinks: bool
        ) -> None:
            if crash_point == "before_link":
                os.kill(os.getpid(), signal.SIGKILL)
            original_link(source, target, follow_symlinks=follow_symlinks)
            if crash_point == "after_link":
                os.kill(os.getpid(), signal.SIGKILL)

        def interrupted_sync(directory: Path) -> None:
            original_sync(directory)
            if (
                crash_point == "after_cleanup"
                and directory == artifact.path.parent
                and not artifact.path.exists()
            ):
                os.kill(os.getpid(), signal.SIGKILL)

        with (
            patch.object(os, "link", interrupted_link),
            patch.object(artifacts, "sync_directory", interrupted_sync),
        ):
            artifacts.finalize_output(connection, task, artifact)


if __name__ == "__main__":
    main(sys.argv[1:])
