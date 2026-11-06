## Architecture

- SQLite owns the queue and step ledger; workers claim tasks, and a shared run lock prevents recovery while an earlier worker survives.
- Inspection and analysis produce a frozen identity snapshot before rewriting, saved-output verification, publication or quarantine, and report reconciliation.
- Input bytes, configuration and secret-key identity bind each run; fenced attempts, atomic successors and durable checkpoints support replay.
- Large artifacts stay on private disk; CSV checkpoints use complete record boundaries, with one inference worker and one light worker limiting model duplication.

## Stack

- SQLite WAL and short transactions avoid external services; writes still serialize, and state grows with identity evidence.
- Pydantic validates contracts, TOML holds configuration, and AES-GCM protects identifying state using environment-supplied secrets.
- GLiNER PII Edge UINT8 is selected for local NER: 69.2% exact recall at 195.6 MiB in isolation, outperforming the measured small local alternatives on recall and memory balance.
- PP-OCRv5 mobile English is selected for local OCR: 44/52 identifiers localized versus Tesseract's 36/52, with 343.7 MiB isolated peak memory.
- GLM 5.3 Flash is selected for optional hosted text: the highest measured exact-span F1 (75%), with greater latency; NER scores do not validate an LLM judge.
- The OpenAI SDK wrapper provides encrypted response replay, bounded backoff, circuit state and shared cost reservations; PyMuPDF is selected under its AGPL license.

## Choices

- Typed fields use deterministic transformations; optional hosted detection and judging obey the global model-disable switch and require local fallback.
- Verification checks intact and Unicode-normalized source and saved text, including unknown column labels; identifying evidence must fit a complete edit span, and failures or unknown coverage quarantine.
- Scoped identifiers and corroboration link identities; names alone do not, conflicting middle names cannot bridge through shorter spellings, and provider roles stay separate.
- Linked patients share a date offset; ages at or above 90 become 90+, revealing birth dates are generalized, and unrepresentable native bounds quarantine.
- ZIP codes use permitted three-digit prefixes or 000; clinical codes, values, units, medications and diseases retain their content.
- Device production identifiers and ambiguous lots are pseudonymized; known shared medication batches remain unless patient linkage is evident, following the [HHS distinction](https://www.hhs.gov/hipaa/for-professionals/faq/can-device-identifier-di-portion-unique-device-identifier-udi-be-part-limited-or-de-identified/index.html).
- Valid mislabeled files retain their detected native format and original name; corrupt files and unassessed hidden surfaces fail closed.
- XLSX verification accounts for XML names, metadata and ZIP contents, rejects ambiguous cells, and compares unedited layout and styles with the source.
- Saved remote responses replay; a crash before persistence may require another bounded request, a different answer or another charge.

## Measurements

- Initial offline CSV baseline: 30,000 rows / 5,753,686 bytes in 38.41 seconds, 781 rows/s and 344.4 MiB peak under 2 vCPUs / 1 GiB; all rows published, with no OOM or model charge ([record](benchmarks/baseline-30000.json)).
- Four local NER candidates, four OCR variants and three OpenRouter models were compared on 40 text cases and 12 images; exact models, accuracy, verifier failures, memory and timings are in the [benchmark report](benchmarks/README.md).
- Verifier v3 found zero false accepts on the unchanged 40-case development corpus across four local adapters and three cached hosted configurations, with 0–4 false rejects; macOS regression results include local fallbacks and no new charges.
- Hosted receipts report $0.045215; conservative reservations account for $2.422906. Local runs were container-constrained; hosted client runs used macOS. Neither comparison establishes clinical safety or the 2 GiB / 30 minute target.

## Known limitations

- Current publication covers CSV/TSV, bounded labelled text, supported XLSX and HL7 ADT; other formats and unsupported populated surfaces quarantine.
- Native files default to 32 MiB, expanded archives to 256 MiB and images to 16 million pixels; only CSV rewriting streams beyond the native-file limit.
- Unsupported Office extensions, custom namespace prefixes and part paths quarantine; unsupported international phones and extensions also quarantine instead of accepting a partial replacement.
- The observed name/contact escapes are blocked; unfamiliar entities can still evade shared statistical NER, and overextended model spans can reject clean text.
- The selected GLiNER adapter remains unsupported by the production loader: the default CLI test publishes 0 instead of 4 files; explicit spaCy passes publish and replay. PP-OCR and hosted detection remain benchmark-only.
- OpenMed reached 1 GiB in isolation; NVIDIA full weights were excluded before inference. GLiNER matched upstream on 140 inputs; OpenMed BIO grouping remains experimental.
- Hosted publication integration, remote judging, pixel verification, cross-issuer linkage, collision auditing, the shared-medication-batch exception and full-run crash equivalence remain incomplete or unvalidated; legacy XLS is unsupported.
- Atomic installation requires one filesystem; replay needs state and the original secret. Output ownership blocks mixed runs; input, policy or configuration changes require a fresh output workspace.
