# Architecture and decision log

Updated: 2026-11-06

This log records the architecture decisions I have made, their rationale, and the
known limitations of the implementation. I distinguish implemented behavior from
design decisions whose implementation is still pending.

## Resource constraints and incremental development

I am designing for a container with 2 vCPUs and 1 GB of RAM, with runtime network
access limited to the supplied model endpoint. These constraints led me to choose
embedded persistence, local files for artifacts, bounded processing, and optional
hosted-model assistance.

I built the queue and durability layer first, then added coordinator startup and
placeholder workers. This lets me test task ownership and recovery before adding
clinical transformations. I keep changes small and cohesive so I can review and
roll back each milestone independently.

## Functional code and module boundaries

I use functional, composable Python with explicit dependencies, type annotations,
and small modules grouped by responsibility. Business logic and the worker-facing
persistence API are functions. I use frozen Pydantic models for structured data
and pass third-party runtime objects into functions without adding manager or
client wrapper classes.

I keep coordinator code in `src/redactor/coordinator/`, worker execution in
`src/redactor/workers/`, and shared schemas in `src/redactor/schemas/`. Named
constants live in `src/redactor/utils/constants.py`, grouped by responsibility.
Error codes and their allowed values live in `src/redactor/utils/errors.py`.

I avoid mutable global runtime state, global connections, and import-time I/O.
File locations and configuration defaults are named constants. I introduce an
abstraction only when it addresses a concrete need. For agent code, I have chosen
to separate prompts, output schemas, transport/runtime, and agent-specific logic.

I annotate context-manager generators with `Generator`. Ordinary lazy database
iterators remain iterators; listing tasks does not claim them.

I support Python 3.11 and later, with Python 3.14 selected for development. Ordinary
Python 3.14 still has a GIL, so I use separate worker processes rather than relying
on a free-threaded interpreter. I use the project virtual environment for editor
diagnostics and command-line tools. Ruff handles linting, formatting, and
annotation presence; type checking is a separate check.

## SQLite as the authoritative queue

I chose SQLite as the durable queue and execution ledger. It stores task
identities, dependencies, attempts, statuses, file locations, and artifact
metadata. Queue state does not depend on an in-memory queue or JSON files.

An embedded database avoids running Redis, a message broker, or PostgreSQL within
the small container. I use direct SQLite operations and numbered SQL migrations;
the current persistence layer does not need an ORM.

Each worker owns a connection. I use short `BEGIN IMMEDIATE` transactions for
claims and state transitions. Hashing, parsing, model calls, and file writes take
place outside database write transactions.

I enable WAL at database setup, including single-worker runs. It allows readers
alongside a writer, but SQLite still has one writer at a time. I also configure
`synchronous=FULL`, foreign keys, a bounded lock wait, a suggested page-cache size,
and file-backed temporary storage.

**Intentional tradeoff:** I accept serialized, short database writes in exchange
for a small embedded dependency and transactional state. Worker computation can
still run concurrently. This deployment does not require PostgreSQL's
`SKIP LOCKED` mechanism or a distributed scheduler.

## Task identity and queue granularity

I represent one step for one input as a task. Its identity includes the resolved
input path, the input's SHA-256 digest, the step, and the processing version.
Repeated registration preserves an existing task's state. A different input,
step, or processing version produces a different task.

I keep registration and artifact helpers in `persistence/files.py`. Registration
hashes raw bytes in bounded buffers, checks for changes during hashing, and stores
the task and its temporary/output locations together. It creates no output file.
These hashes establish file identity; I do not use them as pseudonyms for PHI.

The processing version identifies the configuration relevant to a result. A key
version can contribute to that identity without storing the secret itself.

I chose to queue file references and step metadata, with bounded record or chunk
processing inside a step. I do not enqueue file contents or create an independent
task for every CSV row. The current implementation supports file-step tasks;
record processing is not implemented yet.

## Explicit claims and durable step completion

I expose a functional worker API through `persistence/client.py`. Workers pull
ready tasks from SQLite and explicitly claim, complete, or fail them. Opening or
closing a queue connection does not acknowledge a task.

A claim selects a pending task whose prerequisites succeeded and records a new
attempt token. Workers can restrict claims by step and processing version. I use
the token to reject completion from an old attempt after ownership changes.

`complete_task(..., result=..., successors=...)` accepts a step result and enqueues
its dependent successors in one transaction. Successful committed steps survive
recovery. I require an explicit retry for failed tasks; rediscovery does not retry
them silently. Failure records use registered codes rather than raw exception text.

Recovery marks running attempts interrupted and returns their tasks to pending.
I invoke it only after establishing exclusive recovery ownership. Opening the
database alone never resets work.

I distinguish one accepted logical result from exactly-once execution. CPU work,
console output, or external calls can repeat after interruption. Processing
functions must therefore make their side effects repeatable.

## Recovery ownership and the coordinator

I keep the coordinator as a thin entry point for directory validation, run
ownership, database setup/migration, recovery, inventory, worker startup, and
supervision. Workers execute individual tasks and report completion through SQLite.

Inventory walks inputs without filtering by extension and registers them before
workers start. I reject symlinks and nonregular entries during bootstrap
inventory. Workers do not start after a partial inventory.

I use a POSIX run lock held by the coordinator and inherited by its workers. This
prevents a replacement coordinator from resetting tasks while a worker from the
previous run survives. The lock protects recovery ownership; database transactions
and task claims still control individual work.

I start workers in fresh interpreters, each with its own database connection.
Only the ownership descriptor is explicitly inherited. Ownership is released by
closing descriptors, not by unlinking the lock file or explicitly unlocking a
shared descriptor. Startup can remain blocked until surviving old workers exit.

The current workers claim `print_task` for `bootstrap-v1`, print safe task metadata,
and complete that diagnostic step. Prints can repeat after a crash before the
completion commit. An empty ready queue ends a bootstrap worker; this is not a
general termination rule for a multi-stage pipeline.

Worker failure stops the group, and normal termination signals trigger bounded
cleanup. I target local POSIX filesystems on Linux and macOS.

## Filesystem artifacts and publication

I store large artifacts on the filesystem and keep references and integrity
metadata in SQLite. SQLite can store blobs, but this arrangement keeps large
intermediate files outside its write transactions and journal.

Each attempt has its own private temporary file. Reopening that path preserves
its bytes; it does not establish that appending is safe. A new attempt gets a new
path. I seal an artifact by closing the writer, syncing the file, and hashing it.

My publication helper installs the supplied artifact with an atomic hard link,
without overwriting a conflicting output. It syncs the output directory before
removing the temporary link, then syncs the temporary directory. Replaying
finalization accepts identical installed bytes, including after interruption
between installation and cleanup.

**Intentional tradeoff:** I require temporary and output paths to share a local
filesystem. Cross-filesystem publication fails rather than falling back to a copy
that could expose a partial file.

Filesystem operations and SQLite completion are separate durability boundaries.
I persist bytes before recording their metadata. The current finalization helper
checks byte integrity; it does not establish that an artifact is free of PHI.

For the clinical pipeline, I have chosen staging followed by independent
verification, then publication or quarantine. Temporary data must remain available
until the durable outcome no longer needs it for recovery. This workflow is not
implemented yet.

## Recovery within long steps

I have chosen checkpoint-based recovery for long-running steps so a restart does
not always repeat the entire file or completed model work. A checkpoint table and
schema exist, but saving and resuming checkpoints is not implemented.

The design requires durable output before a checkpoint is accepted, and recovery
must validate the committed prefix before continuing. A temporary file's existence
alone is not a valid checkpoint.

I require parser-defined record boundaries. CSV may contain quoted newlines, and
general JSON cannot resume at an arbitrary byte offset without parser state.
A buffered stream position alone is therefore insufficient.

## State location and migrations

I use `.redactor` as the default private state directory, with `--state` as an
optional override for deployment and persistent-volume placement. Resume requires
retaining that directory and SQLite's journal files across restarts. Private
filesystem permissions protect state, but do not encrypt it.

I keep numbered SQL migrations in `src/redactor/migrations/`. The package discovers
and validates consecutive versions, then derives the latest schema version from
those files. I do not maintain a separate version registry. Migration naming
constants remain grouped in the central constants file.

Pending migrations and SQLite's `user_version` update run in one transaction.
I reject unsupported newer databases and add new migrations instead of changing
applied ones.

## Actual file types and native representations

I have chosen to route files by their validated actual format rather than their
extension. A valid workbook named `.csv` belongs to the workbook adapter; DICOM
content named `.dat` belongs to the DICOM adapter. A misleading extension alone
does not justify quarantine. These format adapters are not implemented yet.

I will preserve the actual native format and required final filename, reporting
the detected type and mismatch. A correctly suffixed private working copy can
accommodate library requirements. Flattening a workbook into CSV merely to match
its name could discard content. Corrupt or unsupported content belongs in
quarantine rather than being silently repaired into an incomplete output.

I have chosen text as a shared analysis representation, with native locations and
context retained for rewriting. The design includes structured fields, hidden surfaces,
metadata, embedded content, and pixels. Visible text extraction alone is not
sufficient coverage.

## Deterministic detection and interchangeable models

I have chosen deterministic handling for typed fields and recognizable patterns
where it is sufficient. Explicit name fields do not need NER to discover their
type. Date parsing and defined identifier formats can use field meaning,
validation rules, and applicable checksums.

A pattern match alone does not authorize replacement. Clinical codes,
measurements, medications, and other protected values must survive. Structured
files can still contain free text and embedded content that require contextual
inspection.

I have chosen composable functional adapters for local NER and OCR so I can replace
and benchmark implementations independently. Loaded runtime objects are explicit
dependencies, reused across bounded units. Model-specific tokenization, batching,
and coordinate/offset conversion belong inside each adapter. Shared findings carry
source locations, entity types, and evidence. Detection, replacement planning, and
native writing remain separate responsibilities. These adapters are not yet
implemented.

## Identity and replacement boundaries

I treat entity resolution separately from detection. A name plus a reliable,
correctly scoped unique identifier can establish straightforward matches; a name
alone does not establish a unique person. Supported aliases must share a
consistent identity while distinct people remain separate.

I have chosen deterministic replacement independent of the detector that found a
value. Replacements must preserve the required shape and format. Patient-specific
date handling must remain consistent across representations. Secrets belong in
environment configuration, never in logs, reports, source code, or task identities.
The clinical replacement layer is not implemented yet.

## Hosted models and the structured-data path

I have chosen a small functional helper around the OpenAI SDK for the configured
endpoint, with transport separate from prompts and output schemas. The endpoint
determines compatibility and vision support. The helper is not implemented yet.

The structured-data path is designed to work with hosted calls disabled. I chose
bounded streaming and local contextual processing, covering every row and
free-text field without a hosted request per cell. CSV/TSV record parsing, general
JSON parsing, and spreadsheet handling require their respective adapters.

Hosted assistance is optional for difficult contextual or image cases. A model
outage must not lower the publication standard. Runtime assets needed for local
processing must be available without additional network destinations.

I do not claim exactly-once remote execution or billing. A crash after a remote
request completes but before local persistence can cause a repeat request or a
different response. SQLite and temperature zero do not remove that boundary.

## Verification and reporting

I have chosen independent verification of the serialized artifact as a required
publication gate. Verification must establish its own evidence, check native
validity and protected clinical values, and distinguish expected surrogates from
original identifiers. A failed or incomplete verification cannot authorize
publication.

Reports derive counts from durable accepted state and reconcile every input with
a terminal outcome. The design records actual type, status/reason,
detected/applied/verified counts, timing, and model usage/cost without exposing PHI.
Verification, quarantine, and reporting are not implemented yet.

## Validation approach and current limits

I use small commits with semantic messages and tests for behavior, failures,
retries, stale attempts, and crash boundaries. The existing tests cover queue
transitions, migrations, file integrity, and selected real subprocess interruption
boundaries. They do not establish clinical safety or full-pipeline crash equivalence.

I have chosen to compare interchangeable model adapters on the same inputs using
identifier recall, changes to protected clinical content, latency, throughput,
and peak container memory. The required large-file benchmark covers the complete
2 GiB path, including verification and reporting, under the actual CPU/RAM limits
with zero hosted calls. No end-to-end performance result is available yet.

The current implementation is an execution foundation. Clinical processing,
general stage scheduling, checkpoint save/resume, and general temporary-file
cleanup are absent. The artifact finalizer is attempt-scoped and does not yet
provide durable handoff between separate rewrite, verify, and publish tasks.

Registered output paths currently use the original basename. Nested inputs with
the same basename can target the same output; conflicting bytes are rejected.
Task identity includes the resolved absolute input path, so relocating inputs
changes that identity. Recovery requires retained local state and old workers
releasing ownership. It does not provide backup, disaster recovery, or multi-host
execution.
