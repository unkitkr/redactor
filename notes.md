## Architecture

- Native extraction, redaction, saving and independent verification precede publication; unsafe files quarantine and every input is reconciled.
- SQLite WAL, complete-record checkpoints, encrypted evidence, atomic artifacts and an inherited run lock protect recovery.
- Replay freezes inputs, runtime, configuration, models and key; native Linux storage avoids observed macOS bind-mount database corruption.

## Stack

- GLiNER Edge UINT8 and PP-OCRv5 English detect; independent spaCy and Tesseract verify, with ZXing-C++ and YuNet for barcodes and faces.
- Optional GLM 5.3 Flash uses encrypted replay, bounded retries, local fallback and a shared $3 budget; local mode makes zero calls.
- Python, Pydantic, TOML and AES-GCM provide contracts and protected state; parsers include PyMuPDF (AGPL), pydicom, lxml and openpyxl.

## Choices

- Content determines format, including mislabeled files; only assessed native structures publish.
- Corroborated identifiers link patients; names alone cannot merge identities. Providers remain separate even when one human has both roles; unlinked people retain contextual identities.
- Patient dates share an offset; unattributable dates use stable record/document context. Exactly 90 and older become 90+, with bounded birth dates; FHIR uses explicit extensions.
- ZIPs retain permitted prefixes or 000. Smaller geography, lots and device identifiers are pseudonymized; clinical codes, values, units, medications and diseases remain unchanged.
- Pixel PHI is masked; PNG/TIFF preserve other pixels exactly, JPEG retains codec loss. DOCX drops unused previews; hidden surfaces still require verification.

## Measurements

- Two CPUs / 1 GB / no swap: [local](benchmarks/held-in-local-v25.json) published 5/12 in 27.18 s at 803.43 MiB; [hosted](benchmarks/held-in-hosted-v25.json) also 5/12 in 562.21 s at 768.57 MiB, 162 attempts, $0.0208 receipts ($0.0344 bound). Replays added no attempts.
- [40 development cases](benchmarks/accuracy-v25.json): precision 83.78%, recall 79.49%, F1 81.58%; no labelled clinical overlap; zero false accepts / one false reject in 34 checks.
- [2 GiB v18 failed](benchmarks/large-csv-2g-v18.json): 11.2 million rows, 1,800.25 s timeout, 1.82 million analyzed, none published, approximately 1 GB peak and 3.07 GB state.

## Known limitations

- Six valid inputs quarantine; statistical misses and false positives remain. These reused text cases are not full-document ground truth.
- Native limits: 32 MiB files, 256 MiB expanded archives, 16 million image pixels; unsupported structures quarantine. FHIR bounds need downstream interpretation; cross-issuer linkage and collision auditing remain incomplete.
- Two [full-set SIGKILLs](benchmarks/crash-replay-v25.json) reproduced clean artifact bytes, not exhaustive crash coverage. Atomic publication requires one filesystem; lost remote responses can incur repeat charges.
- Bulk throughput, hosted judging, hosted vision and broader format support remain incomplete; [requirement coverage](docs/requirements.md) distinguishes implemented paths from demonstrated results and omissions.
