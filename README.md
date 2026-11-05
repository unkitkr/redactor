# Redactor

Local building blocks for the PHI pseudonymization assignment. The current
implementation is the durable queue and state foundation. The coordinator,
orchestration, workers, and clinical processing will be implemented separately.

## Development

Use `uv sync` to install the locked dependencies. `.python-version` selects Python
3.14 for development; the package supports Python 3.11 and later. Ordinary Python
3.14 still has a GIL. Planned CPU workers use separate spawned processes, so they
do not share one GIL; a free-threaded interpreter is not required.

Pyrefly uses the project interpreter at `.venv/bin/python`, configured in
`pyproject.toml`. Select that interpreter in the editor as well. If diagnostics
still show packages from a standalone interpreter, restart the language server.

```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy src tests
uv run pytest -q
```

## Durable queue

```python
from contextlib import closing
from pathlib import Path

from redactor.persistence.database import open_database
from redactor.persistence.files import register_file
from redactor.persistence.queue import (
    claim_task,
    complete_task,
)

with closing(open_database(Path(".redactor"))) as connection:
    register_file(connection, Path("input/encounters.csv"), "inspect", "policy-v1")
    claimed = claim_task(connection)

    if claimed is not None:
        # Perform the metadata-only inspection before accepting its completion.
        # Persist and validate an output artifact before accepting a file result.
        complete_task(connection, claimed)
```

`register_file` hashes the input in bounded buffers outside any write transaction,
then stores the task and its temporary/output locations in one commit. Locations
come from `utils/constants.py`: temporary artifacts live under
`<state>/tmp/<task_id>/`, and outputs target the workspace's
`output/published/<original_name>`. Registration creates no output files.

`prepare_task`, also in `persistence/files.py`, prepares metadata for callers that
need to enqueue successors atomically through `complete_task`.
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

## Temporary files and outputs

`create_temporary_file(connection, claimed)` creates a private file named by the
attempt token under its registered temporary directory. Repeated calls preserve
existing bytes, and a new attempt gets a separate file. This does not implement
checkpoint recovery or decide where appending is safe.

Close the writer, then call `seal_temporary_file` to sync and fingerprint its
bytes. The future independent verifier must approve that exact artifact before
the caller passes it to `finalize_output`. Finalization rechecks the bytes and
installs the complete file at its registered output path. These helpers do not
perform PHI verification themselves.

An atomic hard link installs the output without overwriting a conflicting file;
the output directory is synced before the temporary link is removed. Replaying
finalization accepts an identical existing output, including after a crash between
installation and cleanup. The temporary and output paths must share a local
filesystem. Cross-filesystem publication fails without creating a partial file.

The caller owns exclusive coordination, closes writers before verification, and
keeps artifacts unchanged until finalization finishes. Filesystem finalization and
SQLite task completion are separate operations: pass the returned artifact to
`complete_task` after successful finalization. Actual verifier execution, startup
reconciliation, and checkpoint save/resume will be implemented separately.

## Layout

- `src/redactor/utils/constants.py`: named defaults, file locations, and states.
- `src/redactor/utils/errors.py`: failure codes and allowed failure-code lists.
- `src/redactor/schemas/persistence.py`: task, attempt, checkpoint, and artifact models.
- `src/redactor/persistence/database.py`: schema and transaction boundaries.
- `src/redactor/persistence/queue.py`: task transitions and attempt history.
- `src/redactor/persistence/files.py`: file registration and artifact persistence.
- `src/redactor/utils/filesystem.py`: shared private-directory and sync operations.
- `src/redactor/coordinator/`: reserved for the later coordinator implementation.
- `tests/`: real temporary SQLite databases and files.

Agent prompts, output schemas, and runtime code will be introduced separately
when a real agent is implemented, following `AGENTS.md`.
