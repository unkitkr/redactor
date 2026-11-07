## Architecture

- Native extraction, redaction, saving and independent verification precede publication; every input publishes or quarantines with a reason.
- SQLite WAL, record-boundary checkpoints, encrypted evidence, atomic artifacts and an inherited run lock protect recovery.
- Replay freezes inputs, code, configuration, models and key; native Linux storage avoids observed macOS bind-mount database corruption.
- Native labels and bounded document context support detection; bounded verification batches retain exact text, saved-byte checks and row coverage.
- A separate [direct-function experiment](simple_pipeline/) removes execution infrastructure while retaining native processing and verification; it deliberately has no recovery or bulk guarantees.

## Stack

- GLiNER Edge UINT8 and PP-OCRv5 detect; independent spaCy and Tesseract verify, with ZXing-C++ and YuNet for barcodes and faces.
- Optional GLM 5.3 Flash uses encrypted replay, retries, local fallback and a shared $3 budget; local mode makes zero calls.
- Python, Pydantic, TOML and AES-GCM provide contracts and protected state; native parsers include PyMuPDF (AGPL), pydicom, lxml and openpyxl.

## Choices

- Content determines format, including mislabeled files; only assessed native structures publish.
- Corroborated identifiers link patients; names alone cannot merge identities. Providers retain a separate namespace; unlinked people retain contextual identities.
- Patient dates share an offset; unattributable dates use stable context. Exactly 90 and older become 90+; FHIR extensions and DICOM annotations express bounded birth dates.
- ZIPs retain permitted prefixes or 000. Smaller geography, lots and device identifiers are pseudonymized; clinical codes, values, units, medications and diseases remain unchanged.
- Pixel PHI is masked; PNG/TIFF preserve other pixels exactly, JPEG retains codec loss. DOCX drops unused previews; hidden surfaces still require verification.

## Measurements

- Two CPUs / 1 GB / no swap: [local](benchmarks/held-in-local-v28.json) published 6/12 in 21.32 s at 801.74 MiB; [hosted](benchmarks/held-in-hosted-v28.json) 5/12 in 408.58 s at 802.29 MiB, 121 attempts and $0.0215 receipts ($0.0293 bound).
- [100,000 complete CSV rows](benchmarks/bulk-100k-v29.json): 286.56 s, 970.94 MB peak, zero remote calls; verification took 178.70 s. The [full 2 GiB attempt failed](benchmarks/large-csv-2g-v18.json) its 30-minute gate.
- [40 development cases](benchmarks/accuracy-v28.json): precision 86.11%, recall 79.49%, F1 82.67%; no labelled clinical overlap or false verdicts among 35 verifier checks.

## Known limitations

- Five valid supplied files quarantine locally. Statistical misses and false positives remain; the reused text corpus does not establish full-document recall.
- Hosted fallback covers request/schema/span failures; semantic ambiguity still quarantines. Hosted judging and vision, cross-issuer linkage and collision auditing remain incomplete.
- Native limits are 32 MiB files, 256 MiB expanded archives and 16 million image pixels; unsupported structures quarantine. Age bounds require downstream interpretation; clinical syntax checks do not validate complete terminology dictionaries.
- [Two SIGKILL recoveries](benchmarks/crash-replay-v28.json) reproduced all artifact bytes; this is not exhaustive crash coverage. Atomic publication needs one filesystem; lost remote responses can incur repeat charges.
- [Requirement coverage](docs/requirements.md) separates demonstrated results from omissions. Bulk throughput remains below the required gate.
