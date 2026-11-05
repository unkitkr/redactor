## Architecture

- The coordinator handles startup, recovery, and worker supervision; workers pull tasks from the queue.
- A shared run lock prevents recovery while workers from an earlier run are still alive.
- Each task represents one processing step for one file; large files are processed in chunks rather than queued row by row.
- Stable task identities prevent duplicate registration and preserve completed work across restarts.
- Completing a step and creating its dependent tasks happen in one transaction.
- A retry may repeat execution, but only one result is accepted; remote calls can still be billed again.
- Long steps are designed to resume from record checkpoints; checkpoint recovery is not implemented yet.
- Files are validated and handled according to their actual format, even when the extension is wrong.
- Processing preserves native formats and covers text, metadata, embedded content, and pixels.
- Typed fields and known patterns use deterministic detection; free text needs contextual inspection.
- NER and OCR models sit behind interchangeable adapters so they can be compared or replaced independently.
- Person matching is separate from detection and uses scoped identifiers and supporting evidence, not names alone.
- Replacements are deterministic, date offsets stay consistent per patient, and secrets come from the environment.
- Structured files are streamed without skipping rows and must work with hosted models disabled.
- Outputs are verified before publishing; unsafe or unverifiable results go to quarantine.
- Reports use committed state so retries do not duplicate counts.
- Clinical processing, verification, and reporting are not implemented yet; end-to-end benchmark results are not available.

## Technology choices

- SQLite for the queue and state, avoiding extra services within the 2 vCPU and 1 GB limit.
- WAL and short transactions for concurrent workers, accepting that SQLite serializes database writes.
- Local files for large artifacts and SQLite for their references; recovery requires retaining both.
- Atomic publication on the same filesystem to prevent partial outputs; cross-filesystem publication is unsupported.
- Numbered SQL migrations without an ORM, keeping the persistence layer small.
- OpenAI SDK for optional hosted-model calls through the supplied endpoint.
