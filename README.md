# Redactor

PHI pseudonymization with durable SQLite tasks, identity resolution, saved-file
verification and publication or quarantine. Current publication covers supported
CSV/TSV, labelled text, XLSX and HL7 ADT; unsupported formats and surfaces
quarantine. See [notes.md](notes.md) for measured limitations.

## Run the pipeline

Set `REDACTOR_SECRET_KEY` to a base64-encoded 32-byte secret and retain it for
replay. The checked-in configuration uses GLiNER PII Edge UINT8. Stage its pinned
`gliner_config.json`, `tokenizer.json` and `onnx/model_quint8.onnx` under
`.models/gliner-pii-edge-v1.0/` before running. Checksums and download URLs are in
[the model manifest](benchmarks/model-artifacts.json); the setup helper
`uv run python tools/benchmarks/fetch_models.py` fetches all benchmark artifacts.
Runtime loading never downloads models. In a container, mount the staged directory
read-only at `/work/.models` and retain the same weights for replay.

The shared functional loader supports GLiNER and spaCy with input bounds,
validated spans and per-worker caching. Missing or incompatible weights and failed
inference prevent publication when a model is required. GLiNER also rejects inputs
outside its token window without truncating them. Its additional detections can
trigger conservative quarantine when rewriting cannot establish safe coverage.
For the established spaCy path, use a separate TOML configuration containing:

```toml
[local]
ner = "spacy"
[remote]
enabled = false
```

Pass that file with `--config <path>`. The ordinary entry point is:

```bash
uv run redactor --input input --state .redactor --workers 2
```

`uv run python -m redactor` provides the same entry point and defaults. The
coordinator validates directory locations, acquires exclusive run ownership,
initializes SQLite, recovers interrupted tasks, and registers input files before
starting workers. Inventory walks nested directories without filtering by file
extension or loading entire files into memory. Symlinks and nonregular entries
fail startup; workers do not start after an incomplete inventory.

Each worker opens its own queue connection and completes durable pipeline steps.
Inspection and analysis precede a frozen identity snapshot, rewriting, independent
saved-file verification, and publication or quarantine. A successful run produces
`output/published/`, `output/quarantine/`, `output/report.json` and `output/run.log`
beside the state directory. Reports contain hashes and counts, not raw PHI.

`output/.run-id` binds those files to one inventory, configuration, secret identity
and pipeline version. The same run can resume; a changed run or unowned older
outputs cause `output_content_conflict` before workers start. Use a fresh workspace
for an upgrade, for example `--state tmp/new-run/.redactor`, which writes to
`tmp/new-run/output/`. Existing outputs are never deleted or relabelled.

The optional `--diagnostic` mode retains the queue bootstrap demonstration and
prints task metadata without clinical processing.

The coordinator waits for its workers and stops the group if any worker fails.
SIGINT and SIGTERM trigger bounded cleanup. A persistent lock file under the state
directory prevents two runs from sharing recovery ownership. Workers inherit its
descriptor, so SIGKILL of the coordinator cannot allow recovery to reset work
while a surviving worker still runs. Workers stop taking tasks when their parent
exits; restart after they exit. Never delete the lock file to bypass ownership.
This uses local POSIX filesystem semantics on Linux and macOS.

A crash can repeat a diagnostic console line because printing and SQLite
completion are separate operations. Clinical artifacts use durable checkpoints
and atomic installation instead; full-run SIGKILL equivalence remains a separate
acceptance test, as recorded in the notes.

Coordinator responsibilities are split between `run.py`, `inventory.py`,
`ownership.py`, `processes.py`, `signals.py`, and `cli.py`.

## Development

Use `uv sync` to install the locked dependencies. `.python-version` selects Python
3.14 for development; the package supports Python 3.11 and later. Ordinary Python
3.14 still has a GIL. Workers use separate spawned processes, so they
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

## Model requests

Remote request settings live in `redactor.toml`. `max_attempts` includes the first
call. Transient failures use full-jitter exponential backoff, starting with
`retry_initial_seconds` and capped by `retry_max_seconds`. A server's `Retry-After`
is a minimum wait, even when it exceeds that cap. The total deadline and remaining
cost budget can stop retries sooner. Authentication failures and malformed model
responses fall back immediately. The OpenAI SDK's additional retries are disabled.
Attempt counts, cost reservations, pending retry waits, and the logical request's
deadline persist across worker restarts. Restarting does not grant a fresh retry
or time budget. Only inference workers explicitly load the installed local model. The provider
wrapper is tested, but hosted detection and judging are not integrated into
clinical publication; model comparisons and offline replay live under `tools/`.

## Durable queue

```python
from pathlib import Path

from redactor.persistence.client import claim_task, complete_task, open_queue
from redactor.persistence.files.registration import register_file

with open_queue(Path(".redactor")) as queue:
    register_file(queue, Path("input/encounters.csv"), "inspect", "policy-v1")
    claimed = claim_task(queue, step="inspect", processing_version="policy-v1")

    if claimed is not None:
        # Perform the metadata-only inspection before accepting its completion.
        # Persist and validate an output artifact before accepting a file result.
        complete_task(queue, claimed)
```

`persistence/client.py` exposes a functional worker API: `open_queue`, `claim_task`,
`complete_task`, and `fail_task`. The context owns connection cleanup; each queue
operation owns its short transaction. No transaction stays open while doing work,
and leaving the context never automatically accepts an unfinished task.

`register_file` hashes the input in bounded buffers outside any write transaction,
then stores the task and its temporary/output locations in one commit. Locations
come from `utils/constants.py`: temporary artifacts live under
`<state>/tmp/<task_id>/`, and outputs target the workspace's
`output/published/<original_name>`. Registration creates no output files.

`prepare_task`, also in `persistence/files/registration.py`, prepares metadata for callers that
need to enqueue successors atomically through `complete_task`.
Its identity includes the input path and content, operation, and processing
version. The caller must include relevant policy, identity-map, and key versions
in the processing version, never the secret itself.

`enqueue_task` is idempotent. Dependencies must already exist, and a task's
dependencies cannot change on rediscovery. `claim_task` only selects pending work
whose prerequisites succeeded. An empty ready queue does not mean the entire run
is finished: tasks can still be running or blocked on failed prerequisites.

Each task identifies one step for one input. `complete_task(..., result=artifact,
successors=[...])` records that step's result and inserts dependent tasks in one
transaction. The caller must persist artifact bytes before recording their
metadata. A committed step is preserved on recovery; only interrupted running
steps return to pending. `fail_task` accepts registered failure codes, not raw
exception messages. Failed work requires an explicit `retry_task`; it is not
silently retried by rediscovery.

WAL permits readers alongside a writer; SQLite still permits only one writer at a
time. Connections use explicit short transactions,
`synchronous=FULL`, foreign keys, and a bounded suggested page-cache size.

Opening a database does not claim tasks or recover anything automatically.
`recover_interrupted` is an explicit state transition: it marks running attempts
interrupted and makes their tasks pending again. Coordinator startup establishes
exclusive ownership before invoking it. Old attempt tokens
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

## Schema migrations

Numbered SQL files and their runner live in `src/redactor/migrations/`. The package
owns discovery, filename validation, and migration execution. Naming constants are
grouped in `utils/constants.py`. The package discovers the SQL files
at database startup, orders them by version, and validates consecutive numbering
from one. Their count determines the current schema version. Adding the next SQL
file requires no registry or version-constant update. Add a new migration when
changing the schema rather than editing an existing migration. SQL files are
packaged with the application.

Database startup applies pending migrations and updates SQLite's `user_version`
inside one transaction. A failed migration leaves the prior schema and version
intact. Databases with a newer, unsupported schema are rejected. Each SQL statement
in a migration must end with a semicolon on its own statement's final line.

## Layout

- `src/redactor/utils/constants.py`: constants grouped by domain and responsibility.
- `src/redactor/utils/errors.py`: failure codes and allowed failure-code lists.
- `src/redactor/schemas/persistence.py`: task, attempt, checkpoint, and artifact models.
- `src/redactor/migrations/`: SQL schema changes, discovery, and the migration runner.
- `src/redactor/persistence/database.py`: connection setup and transaction boundaries.
- `src/redactor/persistence/client.py`: functional worker-facing queue API.
- `src/redactor/persistence/queue/`: task transitions, attempt history, and scheduling.
- `src/redactor/persistence/files/`: registration, hashing, artifacts, checkpoints, results, and publication.
- `src/redactor/persistence/runs/`: frozen inventories and run manifests.
- `src/redactor/persistence/models/`: request budgets and encrypted model decisions.
- `src/redactor/utils/filesystem.py`: shared private-directory and sync operations.
- `src/redactor/coordinator/`: startup, inventory, run ownership, and worker supervision.
- `tests/`: real temporary SQLite databases and files.

Agent prompts, output schemas, and runtime code will be introduced separately
when a real agent is implemented, following `AGENTS.md`.
