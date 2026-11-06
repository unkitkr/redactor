## Architecture

- SQLite owns the queue and step ledger; workers claim file steps, and a shared run lock prevents recovery while an earlier worker survives.
- Inspection and analysis feed a frozen cross-file identity snapshot before rewriting, independent saved-output verification, publication or quarantine, and report reconciliation.
- File bytes, configuration and secret-key identity bind the run; task fencing, atomic successors, durable checkpoints and atomic file installation support replay.
- Large artifacts stay on private disk; CSV checkpoints use complete record boundaries, and recovery requires retaining both the database and artifact directory.
- One inference worker and one light worker bound model duplication; reports derive from committed outcomes rather than worker messages.

## Stack

- SQLite WAL with short transactions avoids external services; writers still serialize, and state grows with input and identity evidence.
- Pydantic validates contracts; TOML configures behavior; AES-GCM protects identifying state, with secrets supplied through the environment.
- spaCy small and Tesseract are the selected local baselines; installed model weights require no runtime downloads.
- The OpenAI SDK wrapper provides durable response caching, bounded exponential backoff, Retry-After, shared circuit state and cost reservations.
- PyMuPDF is selected for PDF work under its AGPL license; format adapters retain native containers and original output names.

## Choices

- Typed fields and supported patterns use deterministic transformations; hosted detection and judging have local fallback and obey the global model-disable switch.
- Verification always runs; failed checks or unknown coverage quarantine the original, and surrogate exemptions apply only to complete, specific edit spans.
- Scoped identifiers and corroborating evidence link identities; names alone do not, conflicting middle names cannot be joined through a shorter spelling, and provider roles stay separate.
- Matched patients share one date offset and clinical reference; dates without patient linkage use a separate stable context.
- Ages at or above 90 become 90+; revealing birth dates are generalized, with quarantine when the native format cannot represent the bound; event intervals remain intact.
- ZIP codes become permitted three-digit prefixes or 000; clinical codes, values, units, medications and diseases retain their content.
- Device production identifiers and ambiguous lot fields are pseudonymized; known shared medication batches remain unless patient linkage is evident, following the [HHS distinction](https://www.hhs.gov/hipaa/for-professionals/faq/can-device-identifier-di-portion-unique-device-identifier-udi-be-part-limited-or-de-identified/index.html).
- Valid mislabeled files use their detected native format; corrupt inputs, unsupported populated HL7 fields and unassessed hidden surfaces fail closed.
- A saved remote response replays; a crash before saving may require another bounded request, with a different answer or another charge.

## Measurements

- Initial CSV baseline: 30,000 rows / 5,753,686 bytes in 38.41 seconds, 781 rows/s, 0.143 MiB/s, and 344.4 MiB peak cgroup memory under 2 vCPUs / 1 GiB with networking and remote models disabled; every row was verified and published, with no OOM or model charge ([measurement](benchmarks/baseline-30000.json)).
- Models exercised so far: spaCy `en_core_web_sm` 3.8.0 in the pipeline and Tesseract through PyMuPDF in a single-image OCR probe; accuracy scores and comparisons with other models are not yet established.
- This baseline uses an earlier image; it does not establish performance of the current code or satisfy the required 2 GiB / 30 minute benchmark.

## Known limitations

- Current publication paths cover CSV/TSV, bounded labelled text, supported XLSX parts and supported HL7 ADT fields; other formats and unsupported Office surfaces currently quarantine.
- Native files and individual archive members default to 32 MiB, expanded archives to 256 MiB, and images to 16 million pixels; only CSV rewriting currently streams beyond the native-file limit.
- Local NER and supported clinical patterns are conservative; coded laboratory descriptions outside the recognized vocabulary quarantine, and clinical recall has not been measured against a labelled corpus.
- Writer and verifier share policy functions and local NER, so correlated detection misses remain a risk despite separate serialized-output and residual checks.
- The hosted provider is tested independently but is not yet connected to the publication pipeline; remote judging and OCR verification are not implemented.
- Legacy binary XLS is intentionally unsupported; cross-issuer linkage, a persistent surrogate-collision audit, the shared-medication-batch exception and full-run crash equivalence remain unvalidated or incomplete.
- Atomic installation requires one filesystem; loss of the state directory or the original secret prevents safe replay, and existing conflicting outputs are never overwritten.
