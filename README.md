# Redactor

Local building blocks for the PHI pseudonymization assignment. The current
implementation is the durable queue and state foundation. The coordinator,
orchestration, workers, and clinical processing will be implemented separately.

## Development

Use `uv sync` to install the locked dependencies. `.python-version` selects Python
3.14 for development; the package supports Python 3.11 and later. Ordinary Python
3.14 still has a GIL. Planned CPU workers use separate spawned processes, so they
do not share one GIL; a free-threaded interpreter is not required.

```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy src
uv run pytest -q
```

## Durable queue

```python
from contextlib import closing
from pathlib import Path

from redactor.persistence.database import open_database
from redactor.persistence.queue import (
    claim_task,
    complete_task,
    enqueue_task,
    prepare_task,
)

with closing(open_database(Path(".redactor"))) as connection:
    spec = prepare_task(Path("input/encounters.csv"), "inspect", "policy-v1")
    enqueue_task(connection, spec)
    claimed = claim_task(connection)

    if claimed is not None:
        # Perform the metadata-only inspection before accepting its completion.
        # Persist and validate an output artifact before accepting a file result.
        complete_task(connection, claimed)
```

`prepare_task` hashes the input in bounded buffers outside any write transaction.
Its identity includes the input path and content, operation, and processing
version. The caller must include relevant policy, identity-map, and key versions
in the processing version, never the secret itself.

`enqueue_task` is idempotent. Dependencies must already exist, and a task's
dependencies cannot change on rediscovery. `claim_task` only selects pending work
whose prerequisites succeeded. An empty ready queue does not mean the entire run
is finished: tasks can still be running or blocked on failed prerequisites.

`complete_task(..., successors=[...])` records completion and inserts dependent
tasks in one transaction. `fail_task` accepts registered failure codes, not raw
exception messages. Failed work requires an explicit `retry_task`; it is not
silently retried by rediscovery.

WAL permits readers alongside a writer; SQLite still permits only one writer at a
time. Connections use explicit short transactions,
`synchronous=FULL`, foreign keys, and a bounded suggested page-cache size.

Opening a database does not claim tasks or recover anything automatically.
`recover_interrupted` is an explicit state transition: it marks running attempts
interrupted and makes their tasks pending again. The future runtime must establish
exclusive ownership and stop old workers before invoking it. Old attempt tokens
cannot update current work. This layer accepts one logical result; the future
processing layer must make actual execution repeatable. It cannot guarantee
exactly-once remote API billing.

Keep the state directory and SQLite's journal files together across restarts on
a local filesystem. Do not delete a WAL file manually. The state directory may
contain sensitive paths and intermediate data; it is private and gitignored.

## Layout

- `src/redactor/utils/constants.py`: named defaults, states, and failure codes.
- `src/redactor/schemas/persistence.py`: task, attempt, checkpoint, and artifact models.
- `src/redactor/persistence/database.py`: schema and transaction boundaries.
- `src/redactor/persistence/queue.py`: task transitions and attempt history.
- `src/redactor/persistence/files.py`: bounded hashing and filesystem syncing.
- `src/redactor/coordinator/`: reserved for the later coordinator implementation.
- `tests/`: real temporary SQLite databases and files.

Agent prompts, output schemas, and runtime code will be introduced separately
when a real agent is implemented, following `AGENTS.md`.
