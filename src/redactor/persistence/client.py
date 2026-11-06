"""Small worker-facing API; queue functions own all state-transition rules."""

import sqlite3
from collections.abc import Generator
from contextlib import closing, contextmanager
from pathlib import Path

from redactor.persistence.database import open_database
from redactor.persistence.queue.tasks import claim_task as claim_task
from redactor.persistence.queue.tasks import complete_task as complete_task
from redactor.persistence.queue.tasks import fail_task as fail_task


@contextmanager
def open_queue(state_directory: Path) -> Generator[sqlite3.Connection, None, None]:
    """Provide a process-local queue handle and always close its connection.

    Pass this handle to claim_task, complete_task, and fail_task. Those functions
    use short transactions; no transaction stays open while the worker works.
    Completion supports durable step results and atomically queued successors.
    Exiting this context never acknowledges work automatically. An uncompleted
    claim remains running until explicit startup recovery can safely retry it.
    """
    with closing(open_database(state_directory)) as connection:
        yield connection
