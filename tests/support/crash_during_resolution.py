"""Leave one committed identity batch and kill the process before step completion."""

import os
import signal
import sys
from contextlib import closing
from pathlib import Path

from redactor.persistence.database import open_database
from redactor.persistence.identities.observations import iter_observations
from redactor.persistence.identities.resolution import resolve_batch
from redactor.persistence.identities.sources import initialize_resolution
from redactor.persistence.queue.tasks import claim_task
from redactor.utils.constants import STEP_RESOLVE


def main() -> None:
    with closing(open_database(Path(sys.argv[1]))) as connection:
        task = claim_task(connection, step=STEP_RESOLVE)
        assert task is not None
        dependencies = tuple(
            row[0]
            for row in connection.execute(
                "SELECT depends_on FROM dependencies WHERE task_id = ?", (task.task_id,)
            )
        )
        key = bytes(range(32))
        sources = initialize_resolution(connection, task, dependencies, key)
        for source in sources:
            first = next(iter_observations(connection, source, key), None)
            if first is not None:
                resolve_batch(connection, task, source, (first,), key)
                os.kill(os.getpid(), signal.SIGKILL)
        raise AssertionError("Expected identity observations")


if __name__ == "__main__":
    main()
