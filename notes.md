# Project decisions

Updated: 2026-11-06

This is the ongoing record of decisions made with the user, why they were made,
and the limitations we know about. It records project choices, not raw research.
Update it as decisions change and work is completed.

Status labels distinguish what exists from what we intend to build:

- **Implemented:** present in the repository.
- **Agreed direction:** chosen for future implementation, but not a current capability.
- **Open:** a proposal or question that still needs a decision or evidence.

## Scope and constraints

The target container has 2 vCPUs and 1 GB of RAM. Runtime network access is limited
to the supplied model endpoint. The generated large CSV must cover every row
without sampling or truncation and finish within 30 minutes with hosted models
disabled. Peak memory and throughput must be measured, not inferred from model
download sizes or a small-file test.

We are building in small, reviewable milestones. The queue and durability layer
came first, followed by coordinator startup and placeholder workers. Clinical
processing, general workflow dispatch, checkpoint save/resume, and model execution
are separate milestones. Keeping the existing bootstrap does not authorize
building the entire pipeline in one change.

## Code organization and development

**Implemented conventions, to continue following:**

- Use functional, composable Python with explicit dependencies, clear names,
  type annotations, spacing, and small cohesive modules.
- Keep business logic and worker-facing persistence APIs in functions. Do not add
  manager, service, repository, or client wrapper classes. Frozen Pydantic models
  are used for structured data; third-party runtime objects may be passed into
  functions.
- Group implementation by responsibility. Coordinator code belongs in
  `src/redactor/coordinator/`; worker execution belongs in `src/redactor/workers/`.
  Split files when it improves readability, without creating abstractions merely
  to anticipate possible future use.
- Keep shared schemas in `src/redactor/schemas/`. Put named constants in
  `src/redactor/utils/constants.py`, grouped within that file. Error codes and
  their allowed values belong in `src/redactor/utils/errors.py`.
- Do not use mutable global runtime state, global connections, or import-time I/O.
  Keep file locations and configuration defaults in constants rather than
  scattering magic strings through implementation code.
- When agents are introduced, separate prompts, output schemas, transport/runtime,
  and agent-specific functions. Share code where there are actual common needs.
- Annotate context-manager generators with `Generator`. Ordinary lazy database
  iterators remain iterators; reading task listings does not claim work.

The package currently supports Python 3.11 and later, with Python 3.14 selected for
development. Ordinary Python 3.14 still has a GIL. Separate worker processes avoid
sharing one GIL; a free-threaded interpreter is not a requirement. Use the project
virtual environment so editor diagnostics and command-line dependencies agree.
Ruff handles linting, formatting, and annotation presence; type checking remains
a separate check.

## SQLite owns the durable queue

**Implemented.** SQLite is the authoritative queue and execution ledger. It stores
task identities, dependencies, attempts, statuses, file locations, and artifact
metadata. A disposable in-memory queue is not the source of truth. JSON files are
not used as a replacement for transactional queue state.

We chose an embedded database to avoid running Redis, a message broker, or
PostgreSQL within the small container. Direct SQLite operations and numbered SQL
migrations are sufficient for this layer; no ORM has been introduced.

Each worker owns a connection. Claims and state transitions use short
`BEGIN IMMEDIATE` transactions. Hashing, parsing, model calls, and file writes take
place outside those write transactions.

WAL is enabled at database setup, including single-worker runs. It allows readers
alongside a writer, but SQLite still has one writer at a time. Connections also
use `synchronous=FULL`, foreign keys, a bounded lock wait, a suggested page-cache
size, and file-backed temporary storage.

**Intentional tradeoff:** accept serialized, short database writes in exchange
for a small embedded dependency and transactional state. Worker computation can
still run concurrently. We are not trying to reproduce PostgreSQL's
`SKIP LOCKED` mechanism or build a distributed scheduler.

## File registration and task granularity

**Implemented:** one task identifies one step for one input. Its identity includes
the resolved input path, the input's SHA-256 digest, the step, and the processing
version. Repeated registration preserves an existing task's state. A different
input, step, or processing version is a different task.

File registration and artifact helpers live in `persistence/files.py`. Registration
hashes raw bytes in bounded buffers, checks for changes during hashing, and stores
the task and its temporary/output locations together. It does not create an output
file. File hashes establish byte identity; they are not pseudonyms for PHI.

Relevant policy, identity-map, model/prompt, and key versions will need to contribute
to processing identity when those components are implemented. Store a non-secret
key version, never the secret itself.

**Agreed direction:** queue file references and step metadata, not file contents
or one independent task for every CSV row. Process large files through bounded
records or chunks inside a step. Introduce durable chunk tasks only if a concrete
parallelism or recovery need justifies them.

## Claims, retries, and step-level recovery

**Implemented.** Workers pull ready tasks from SQLite through the functional
`persistence/client.py` API. They explicitly claim, complete, or fail work. Opening
or closing the queue connection does not acknowledge a task.

Claims select pending tasks whose prerequisites succeeded and record a new attempt
token. Workers can restrict claims by step and processing version. An old attempt
cannot accept a result after a new attempt takes ownership.

`complete_task(..., result=..., successors=...)` accepts a step result and enqueues
its dependent successors in one transaction. Committed successful steps survive
recovery. Failed tasks require an explicit retry; rediscovery does not silently
retry them. Failure records use registered codes rather than raw exception text.

Recovery explicitly marks running attempts interrupted and returns their tasks
to pending. It runs only after exclusive recovery ownership is established.
Opening the database alone never resets work.

The guarantee is one accepted logical result with potentially repeated execution.
Processing functions must make their side effects repeatable. This is not a
guarantee that CPU work, console output, or a remote model call runs exactly once.

## Checkpoints inside a step

**Agreed direction, not implemented.** Long steps should eventually resume from
durable progress rather than repeating all parsing, output generation, or model
work. The database has a checkpoint table and schema, but no checkpoint save/resume
API or parser implementation yet.

A future checkpoint needs the durable artifact reference, safe input and output
positions, completed record count, counters, and output-prefix integrity evidence.
Persist the output prefix before committing its checkpoint. Recovery must validate
that prefix and discard any uncommitted output tail before continuing.

A buffered stream position is not automatically a safe record boundary. CSV may
contain quoted newlines, and general JSON cannot resume at an arbitrary byte
offset without parser state. Format adapters must define valid resume boundaries.
The exact checkpoint protocol and frequency remain open.

## Private artifacts and publication

**Implemented foundation.** Large artifacts live on the filesystem; SQLite stores
references and integrity metadata. SQLite can store blobs, but large intermediate
files are kept outside its write transactions and journal.

Each attempt has its own private temporary file. Reopening that path preserves
its bytes; it does not establish that appending is safe. A new attempt gets a new
path. Closing the writer, syncing the file, and hashing it produces a sealed
artifact reference.

Publication helpers install the supplied artifact with an atomic hard link,
without overwriting a conflicting output. They sync the output directory before
removing the temporary link, then sync the temporary directory. Replaying
finalization accepts identical installed bytes, including after interruption
between installation and cleanup.

**Intentional tradeoff:** publication currently requires temporary and output
paths on the same local filesystem. Cross-filesystem publication fails rather
than falling back to a copy that could expose a partial file.

Filesystem operations and SQLite completion are separate durability boundaries.
The caller persists bytes before recording their metadata and must reconcile
interruption between those operations.

**Agreed direction:** rewrite into staging, independently verify the serialized
artifact, then publish or quarantine. Temporary data is removed only after the
durable outcome no longer needs it for recovery. Quarantine handling and general
orphan cleanup are not implemented. Current finalization checks byte integrity;
it does not itself perform PHI verification.

## Coordinator and worker ownership

**Implemented.** The coordinator is a thin entry point for directory validation,
run ownership, database setup/migration, recovery, inventory, worker startup, and
worker supervision. Workers own individual task execution and report completion
through SQLite.

Inventory walks inputs without filtering by extension and registers them before
workers start. Symlinks and nonregular entries fail bootstrap inventory. A partial
inventory does not start workers.

A POSIX run lock is held by the coordinator and inherited by its workers. This
prevents a replacement coordinator from resetting running tasks while a worker
from the previous run survives. It is a recovery-ownership lock, not the SQLite
write lock and not a substitute for claiming tasks.

Workers start in fresh interpreters and open their own database connections.
Only the ownership descriptor is explicitly inherited. Close descriptors to
release ownership; do not unlink the lock file or explicitly unlock a shared
descriptor. Startup may need to wait for surviving old workers to exit.

The present workers only claim `print_task` for `bootstrap-v1`, print safe task
metadata, and complete that diagnostic step. Prints can repeat after a crash
before the completion commit. Empty ready queues end these bootstrap workers;
that behavior is not a general termination rule for a multi-stage pipeline.

Worker failure stops the group, and normal termination signals trigger bounded
cleanup. The current coordination design targets local POSIX filesystems on Linux
and macOS. It does not implement leases or multi-host failover.

## State location and schema migrations

**Implemented.** `.redactor` is the default private state directory. `--state` is
an optional override for deployment and persistent-volume placement, not something
every invocation must supply. Retain the state directory and SQLite journal files
across restarts; deleting them loses resume history. Private filesystem permissions
protect state, but they do not encrypt its contents.

Numbered SQL migrations live in `src/redactor/migrations/`. The package discovers
and validates consecutive versions and derives the latest schema version from
those files. There is no separate hand-maintained version registry. Migration
naming constants remain grouped in the central constants file.

Pending migrations and SQLite's `user_version` update run in one transaction.
Unsupported newer databases are rejected. Add a new migration rather than editing
an applied one. An ORM remains unnecessary for the current schema and operations.

## Actual file format and native content

**Agreed direction, not implemented.** Detect the actual format from bytes and
validate its structure before selecting an adapter. An extension mismatch alone
does not justify quarantine. A valid workbook named `.csv` should use the workbook
adapter; DICOM content named `.dat` should use the DICOM adapter.

Use a correctly suffixed private working copy when a library requires one. Do not
flatten a workbook into CSV merely to match its misleading filename. Preserve the
actual native format and the assignment's required final names, and report the
detected type and mismatch. Corrupt or unsupported content requires an explicit
quarantine outcome rather than a silent, incomplete repair.

Text is a shared analysis representation, but extraction must retain native
locations and context for rewriting. Cells, document text, JSON paths, HL7
components, DICOM elements, image regions, metadata, and embedded content need
their appropriate adapters. Hidden surfaces and pixels cannot be omitted just
because visible text was extracted successfully.

## Deterministic detection and replaceable models

**Agreed direction.** Typed fields and recognizable patterns should use local,
deterministic handling where sufficient. Explicit name fields do not need NER to
discover that they contain names. Date parsing and well-defined identifier formats
can use field meaning, validation rules, and checksums where applicable.

Patterns alone do not authorize replacement. Clinical codes, measurements,
medications, and other protected values must survive. Structured files can contain
unstructured comments, notes, hidden sheets, and embedded objects that still need
contextual inspection.

Build composable functional adapters for local NER and OCR so implementations can
be replaced and benchmarked independently. Pass loaded runtime objects explicitly
and reuse them across bounded units. Keep model-specific tokenization, batching,
and coordinate/offset conversion inside the adapter. Use shared findings schemas
with source locations, entity types, and evidence. Detectors propose findings;
replacement planning and native writing are separate responsibilities.

No final NER or OCR model has been selected. Model research and artifact sizes are
not evidence of recall, throughput, or peak memory in our container. Selection
requires a common evaluation set and the actual worker/runtime configuration.

## Identity, surrogates, and secrets

**Agreed direction:** resolve supported person aliases consistently, keep distinct
people separate, and generate replacements deterministically. A name plus a
reliable, correctly scoped unique identifier can establish the straightforward
cases. A name alone does not establish a unique person. Detection and entity
resolution remain separate responsibilities.

Keep secrets in environment configuration and out of logs, reports, source code,
and task identities. Replacement must preserve the required shape and format.
Patient-specific date handling must be consistent across representations.

**Open implementation proposals:** keyed derivation such as HMAC, domain-separated
identifier/person namespaces, canonicalization, collision handling, realistic
formatters, and key rotation/versioning. Plain encoding or fixed character
substitution is not sufficient protection. These details have not been implemented
or finalized as a complete pseudonymization policy.

The supplied generator chooses MRNs independently of names and birth dates, so
repeated MRNs can carry conflicting demographics. Stable replacement of an
identifier value and resolution of a person are different operations. We still
need a documented deterministic policy for conflicting identifiers, ambiguous
mentions, patient/provider/relative roles, and date ownership. Do not silently
merge conflicting people or hardcode fixture values.

The mechanism for collecting cross-file evidence and committing a stable identity
mapping before dependent rewrites is also open. Any retained raw mappings,
evidence, prompts, and responses are sensitive. Storage protection beyond the
existing private permissions must be decided before retaining those materials.

## Hosted models and offline operation

**Agreed direction.** Use a small functional helper around the OpenAI SDK for the
configured endpoint. Keep transport separate from prompts and output schemas.
Endpoint compatibility and vision support depend on the supplied service. They
do not block building the deterministic structured-data path.

The large-CSV path must operate with hosted calls disabled. Avoid a hosted request
per row or cell. Use bounded streaming and local contextual processing, while
covering all rows and free-text fields. General JSON needs incremental parsing;
XLS and XLSX need their respective adapters rather than whole-file flattening.

Hosted assistance is optional for difficult contextual or image cases. Keep
timeouts, retries, output validation, and cost accounting bounded. A model outage
must not silently lower the publication standard. Local weights and other runtime
assets must be available without downloads from additional network destinations.

**Open implementation details:** SDK retry ownership, persistent response caching,
conservative request-cost reservation, and accounting for uncertain requests.
A crash after remote execution but before local persistence can repeat billing
or produce a different response. Neither temperature zero nor SQLite establishes
exactly-once remote execution without an endpoint contract.

## Verification and reporting

**Agreed direction, not implemented.** Verification is a required pipeline gate
over the serialized artifact. It must establish its own evidence rather than
accepting the detector's claim that everything was replaced. A separate worker
pool is not required merely to make verification independent; scheduling is open.

Publish only a verified artifact. Otherwise retain a machine-readable quarantine
reason. Verification must also check native validity and protected clinical values
and distinguish expected surrogates from residual original identifiers.

Reports should reconcile every discovered input with a terminal outcome and derive
counts from durable accepted state, not console messages. Record actual type,
status/reason, detected/applied/verified counts, timing, and model usage/cost
without exposing PHI. This reporting layer does not exist yet.

## Validation and change management

Commit cohesive, reviewable implementation or documentation chunks using semantic
messages. Preserve user changes. Keep tests meaningful and add coverage for new
behavior, failures, retries, stale attempts, and crash boundaries. Run the checks
appropriate to each change; documentation-only changes need document validation,
not invented runtime tests.

Existing tests cover queue transitions, migrations, file integrity, and selected
real subprocess interruption boundaries. They do not establish clinical safety
or full-pipeline crash equivalence.

Future model benchmarks should compare recall by identifier type, changes to
protected clinical content, latency, throughput, and peak container memory on the
same inputs. Measure the complete 2 GiB path, including verification and reporting,
under the actual CPU/RAM limits with zero hosted calls. No such end-to-end
measurement has been completed yet.

Keep exploratory research artifacts out of published Git history. Review outgoing
history as well as the current tree before any push. This decision record contains
agreed architecture and explicit open choices, not raw research dumps.

If a material implementation decision cannot be made pragmatically from the
assignment and our discussions, pause that implementation and ask the user.

## Known limitations to resolve

These are current gaps, not accepted permanent tradeoffs:

- No clinical processing, general stage scheduler, or checkpoint save/resume yet.
- No final model selection, inference benchmark, or measured full-pipeline memory
  and throughput result.
- No independent verifier, durable verifier verdict, quarantine workflow, report
  reconciliation, or general temporary-file cleanup yet.
- The current artifact finalizer is attempt-scoped. Passing artifacts between
  separate rewrite, verify, and publish tasks needs durable lineage and ownership.
- Registered output paths currently use the original basename. Nested inputs with
  the same basename can target the same output; conflicting bytes are rejected.
  Output namespace handling needs a decision before clinical publication.
- Task identity includes the resolved absolute input path. Relocating inputs
  changes task identity; cross-location resume is not implemented.
- Recovery needs the retained local state and the old workers to release ownership.
  It is not a backup, disaster-recovery, or multi-host execution system.
- Identity ambiguity, collision policy, key lifecycle, and sensitive mapping
  protection still need concrete implementation decisions.
