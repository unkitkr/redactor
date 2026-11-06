## Architecture

- SQLite owns the durable queue; the coordinator handles startup and recovery, and workers claim one file step at a time.
- A shared run lock prevents recovery while workers from an earlier run remain alive.
- Inspection and analysis feed a shared identity-resolution barrier before rewriting, verification, publication or quarantine, and reconciliation.
- A bounded, immutable inventory binds each run to its files, processing policy and secret key; changed inputs or policy create separate work identities.
- Step completion and successor registration are atomic; large files use bounded chunks and parser-aware checkpoints rather than row queues.
- Large artifacts live on private disk with references in SQLite; recovery requires retaining both, and atomic publication requires one filesystem.
- Verification reopens original and output bytes, independently checks native surfaces and clinical preservation, and binds its verdict to the exact artifact.
- Every required verification check must pass; failures and unresolved coverage quarantine the file, and expected surrogates are allowed only at their intended locations.
- One inference-capable worker and one light worker bound model duplication; reports come from committed outcomes and request accounting.

## Stack

- SQLite WAL, short transactions, and numbered SQL migrations avoid extra services and an ORM; writes remain serialized.
- Pydantic validates schemas; TOML configures processing, models, budgets, and resource limits, while secrets remain environment-only.
- The OpenAI SDK targets the supplied endpoint through bounded retries, shared circuit state, and durable cost reservations.
- Transient failures use capped exponential backoff with jitter and Retry-After; attempt counts, pending waits, request deadlines, and cost reservations survive restarts.
- Hosted text calls require configured token prices; byte-based token bounds reserve possible charges, and uncertain requests keep their full reservation.
- spaCy small and Tesseract are the selected local baselines; model packages are pinned at installation and runtime never downloads weights.
- PyMuPDF handles PDF rendering and rewriting under its documented AGPL license, with separate saved-output verification.

## Choices

- Typed fields and supported patterns use deterministic processing; model-dependent work uses the enabled endpoint with local fallback.
- Repeated small text units use a bounded NER cache; oversized units are never silently truncated, and spaCy memory zones release temporary vocabulary.
- Verification always runs; remote judging examines unresolved units only, uses separate configuration, and obeys the global model-disable switch.
- Remote judge findings require location-bound evidence and cannot override failed deterministic checks or unassessed native surfaces.
- Identity matching uses scoped identifiers and corroborating evidence; contradictory people stay separate even when an identifier value receives one consistent replacement.
- Initials require a scoped identifier and one compatible full-name candidate; names alone never merge people, and ambiguous mentions retain separate identities.
- Identity evidence uses encrypted SQLite records with keyed indexes; bounded batches commit evidence and complete-record scan offsets together.
- Frozen identity snapshots exclude rejected sources; matched aliases share one clinical reference date and older-age decision across files.
- Providers have separate pseudonyms; a person appearing as patient and provider retains separate role identities.
- Patient dates share one keyed offset; unattributable dates use a stable separate context, with patient linkage explicitly unresolved.
- Ages of 90 or more become 90+; ZIP codes use permitted three-digit prefixes or 000; clinical codes, values, units, medications, and diseases are preserved.
- Exactly 90 is included; birth dates revealing older ages before or after shifting are generalized against clinical reference dates, with quarantine when a valid native representation is unavailable; clinical event intervals remain intact.
- Device production identifiers and ambiguous lot fields are pseudonymized; known shared medication batches remain unless patient linkage is evident, following the [HHS distinction between model and production identifiers](https://www.hhs.gov/hipaa/for-professionals/faq/can-device-identifier-di-portion-unique-device-identifier-udi-be-part-limited-or-de-identified/index.html).
- Keyed replacements use environment secrets; retained identifying evidence and model responses require encryption and private storage.
- Record identifiers use 18-digit keyed surrogates to reduce collisions; native length limits and collisions must be checked before publication, and provider NPIs retain a valid check digit.
- Private evidence uses AES-GCM with fresh nonces and context-bound keys; only opaque references and safe counters belong in queue metadata.
- Valid mislabeled files retain their actual native format and original output name; corrupt, unsupported, or unverifiable content is quarantined without silent repair.
- Native parser inputs and individual archive members default to 32 MiB, expanded archives to 256 MiB, and images to 16 million pixels; streaming CSV, JSON, and text have separate record limits.
- Nested input paths are preserved under the output root to avoid collisions between files with the same basename.
- Initial coverage targets the supplied file families plus CSV/TSV; legacy binary XLS is explicitly unsupported, and pixel PHI may be masked.
- Large structured files must cover every row and complete verification without hosted calls; local-model quality and the container resource targets remain unmeasured.
- Remote results may drive processing; saved responses replay, while a crash before saving can require a bounded retry with a different answer or another charge.
- The clinical pipeline and its verifier are being implemented; this log describes chosen behavior, not a claim of completed format coverage.
