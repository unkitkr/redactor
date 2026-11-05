"""Small worker-facing API; queue functions own all state-transition rules."""

import sqlite3
from collections.abc import Generator
from contextlib import closing, contextmanager
from pathlib import Path

from redactor.persistence.database import open_database
from redactor.persistence.queue import claim_task, complete_task
from redactor.schemas.persistence import Task


class QueueClient:
    """A scoped connection adapter, restricted to one step and processing version.

    Obtain this client through open_queue and use it only within that context
    and process. Claiming and completing use separate short transactions; no
    database transaction remains open while the caller does its work.
    """

    def __init__(
        self, connection: sqlite3.Connection, step: str, processing_version: str
    ) -> None:
        self._connection = connection
        self._step = step
        self._processing_version = processing_version

    def claim(self) -> Task | None:
        return claim_task(
            self._connection,
            step=self._step,
            processing_version=self._processing_version,
        )

    def complete(self, task: Task) -> Task:
        """Acknowledge a metadata-only step after its work has succeeded."""
        return complete_task(self._connection, task)


@contextmanager
def open_queue(
    state_directory: Path, *, step: str, processing_version: str
) -> Generator[QueueClient, None, None]:
    """Open a process-local queue client and always close its connection.

    Exiting this context never acknowledges work automatically. An uncompleted
    claim remains running until explicit startup recovery can safely retry it.
    """
    with closing(open_database(state_directory)) as connection:
        yield QueueClient(connection, step, processing_version)
