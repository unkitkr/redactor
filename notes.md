## Architecture

- Work follows one path: inspect, analyze, freeze identities, rewrite, verify the saved output, publish or quarantine, then reconcile reports.
- SQLite keeps the queue and step history; workers claim tasks and record progress, while a shared run lock prevents recovery until earlier workers exit.
- Each run is tied to its input bytes, configuration and secret-key identity; durable checkpoints, rejection of stale attempts and atomic step transitions support replay.
- Large artifacts stay on private disk, and CSV checkpoints end at complete records; one inference worker and one light worker limit model duplication.
- Production and evaluation share local adapters: NER checks text spans and caches bounded inputs, while OCR checks image limits and coordinates against source pixels.
- Analysis freezes encrypted detector observations; rewriting replays those observations, while verification independently scans the source and saved output.
- A separate dashboard reads bounded, cached SQLite snapshots; it starts with the coordinator, cannot stop processing on failure, and can be disabled with `--no-dashboard`.

## Stack

- **SQLite WAL** avoids external queue and database services; short transactions keep contention down, but writes still serialize and identity evidence grows the state.
- **Pydantic, TOML and AES-GCM** provide validated contracts, configuration and encrypted identifying state, with secrets supplied through the environment.
- **GLiNER PII Edge UINT8** is the local NER choice for its measured recall and memory balance: 69.2% exact recall at 195.6 MiB in isolation; production coverage remains limited.
- **PP-OCRv5 mobile English** is the OCR choice: 44/52 identifiers localized versus Tesseract's 36/52, at 343.7 MiB isolated peak memory; it is benchmarked but not integrated into publication.
- **GLM 5.3 Flash** is the optional hosted-text choice: the highest measured exact-span F1 (75%), with greater latency; hosted detection is connected to analysis, and these scores do not validate a judge.
- **OpenAI SDK** provides the transport behind encrypted response replay, bounded backoff, circuit state and shared cost reservations.
- **PyMuPDF** is selected under its AGPL license.
- **uv** installs Python dependencies and the packaged spaCy model; other local weights are checksum-verified during setup and mounted before restricted execution, with no runtime downloads.

## Choices

- **File handling:** valid mislabeled files keep their detected native format and original name; corrupt files and unassessed hidden surfaces quarantine.
- **Identity:** scoped identifiers and corroborating evidence link people, never names alone; conflicting middle names cannot link through shorter spellings, and provider roles stay separate.
- **Clinical content:** typed fields use deterministic transformations, while clinical codes, values, units, medications and diseases retain their content.
- **Dates and ages:** linked patients share a date offset; ages at or above 90 become 90+, revealing birth dates are generalized, and formats that cannot represent the required bounds quarantine.
- **Locations:** ZIP codes retain only permitted three-digit prefixes, otherwise 000.
- **Device and batch identifiers:** the policy pseudonymizes device production identifiers and ambiguous lots, while preserving known shared medication batches unless patient linkage is evident, following the [HHS distinction](https://www.hhs.gov/hipaa/for-professionals/faq/can-device-identifier-di-portion-unique-device-identifier-udi-be-part-limited-or-de-identified/index.html); the shared-batch exception remains incomplete or unvalidated.
- **Verification:** intact and Unicode-normalized source and saved text are checked, including unknown column labels; identifying evidence must fit a complete edit span, and failed or incomplete checks quarantine.
- **XLSX verification:** checks cover XML names, metadata and ZIP contents, reject ambiguous cells, and compare unedited layout and styles with the source.
- **Model policy:** local processing is the default; `LLM_ENABLED=1` enables hosted detection with local fallback, while `LLM_ENABLED=0` prevents all remote calls and verification always runs.
- **Hosted limits:** GLM uses a shared $3 run budget, three attempts, a 65-second request deadline and routing caps of $0.15/$0.50 per million input/output tokens; reasoning uses the output allowance ([rates](https://openrouter.ai/api/v1/models/z-ai/glm-5.3-flash/endpoints)).
- **Remote replay:** saved responses are reused; a crash before persistence can require another bounded request, with a different answer or another charge.

## Measurements

- **Model comparison:** four local NER candidates, four OCR variants and three OpenRouter models were compared on 40 text cases and 12 images; exact models, accuracy, verifier failures, memory and timings are in the [benchmark report](benchmarks/README.md).
- **Verifier regression:** v3 found zero false accepts and 0–4 false rejects on the unchanged 40-case development corpus across four local adapters and three cached hosted configurations; these macOS runs include local fallbacks and no new charges, not independent clinical validation.
- **Hosted cost:** receipts total $0.045215, while conservative reservations account for $2.422906; hosted clients ran on macOS, whereas local model comparisons ran in constrained containers.
- **Offline CSV baseline:** all 30,000 rows / 5,753,686 bytes published in 38.41 seconds at 781 rows/s, with 344.4 MiB peak memory under 2 vCPUs / 1 GiB and no OOM or model charge; this does not exercise the 2 GiB / 30-minute target ([record](benchmarks/baseline-30000.json)).
- **Held-in pipeline:** local GLiNER reconciled all 12 supplied files / 533,410 bytes in 2.624 seconds at 572.86 MiB under 2 vCPUs / 1 GiB, but published none; replay added no attempts and preserved all output bytes ([record](benchmarks/held-in-pipeline.json)).
- **Dashboard overhead:** 1,000 tasks under 2 vCPUs / 1 GiB used 0.75% of one core while polling, 43.07 MiB server peak RSS and 40.33 ms mean queue latency; browser overhead and concurrent pipeline throughput were not measured ([record](benchmarks/results/dashboard-overhead.json)).

## Known limitations

- **Publication coverage:** CSV/TSV, bounded labelled text, supported XLSX and HL7 ADT have publication paths; other formats, including legacy XLS, and unsupported populated surfaces quarantine.
- **GLiNER coverage:** a structured CSV with free-text names publishes and replays, but all four valid files in the mixed-format regression still quarantine for unresolved coverage; explicit spaCy publishes those files.
- **Detection limits:** observed name/contact escapes are blocked, but unfamiliar entities can evade shared statistical NER and overextended model spans can reject clean text.
- **Unsupported details:** unsupported Office extensions, custom namespace prefixes, unsupported part paths, and unsupported international phones or extensions quarantine rather than accept partial handling.
- **File limits:** defaults are 32 MiB for native files, 256 MiB for expanded archives and 16 million pixels for images; only CSV rewriting streams beyond the native-file limit.
- **OCR limits:** only single-frame images, aspect ratios up to 64 and at most 256 text regions are accepted, bounding preprocessing and rejecting uncertain partial coverage; image benchmarks do not validate safe image publication.
- **Model headroom:** OpenMed reached 1 GiB in isolation, and NVIDIA full weights were excluded before inference; GLiNER matched upstream on 140 inputs, while OpenMed BIO grouping remains experimental.
- **Validation gaps:** remote judging, pixel verification, cross-issuer linkage, collision auditing and full-run crash equivalence remain incomplete or unvalidated.
- **Recovery boundary:** atomic file installation requires one filesystem, and replay requires the saved state and original secret.
- **Container storage:** SQLite reported corruption on macOS directories shared into Docker Desktop; the same pipeline completed and replayed on native Linux storage, which is required for container state and outputs.
- **Run isolation:** output ownership blocks mixed runs; input, policy or configuration changes require a fresh output workspace.
