## Architecture

- Inputs remain unchanged; native extraction, analysis, rewriting and independent saved-output verification precede publication, with failures quarantined and every input reconciled.
- SQLite WAL owns tasks, checkpoints and encrypted identity/model evidence; complete-record CSV checkpoints and a shared run lock support fenced recovery.
- Runs freeze inputs, code, dependencies, weights, configuration and secret identity; private artifacts and native Linux state storage preserve replay boundaries.

## Stack

- Local detection uses GLiNER PII Edge v1.0 ONNX QUINT8 and PP-OCRv5 mobile English; independent verification uses spaCy `en_core_web_sm` and Tesseract, with ZXing-C++ barcode and YuNet face detection.
- Optional GLM 5.3 Flash text detection uses cached responses, bounded retries, local fallback and a shared $3 budget; local mode makes no remote calls, and no remote judge or vision model is enabled.
- Python, Pydantic, TOML and AES-GCM provide validated contracts and protected state; native libraries include PyMuPDF under AGPL, pydicom and openpyxl, with verified weights staged before execution.

## Choices

- Adapters cover CSV/TSV, text, JSON/FHIR, HL7, XLSX, DOCX, PDF, DICOM and JPEG/PNG/TIFF within explicit format limits; detected formats survive misleading filename extensions.
- Scoped identifiers and corroborating evidence link patients across files; names alone cannot merge identities, provider roles stay separate, and unlinked mentions retain contextual surrogates.
- Linked patients share date offsets; unattributable dates use stable record/document context; ages at least 90 become 90+, revealing birth dates become bounds, and ZIP codes retain only permitted prefixes. FHIR uses custom extensions for the 90+ band and inclusive birth-year bound.
- Clinical values, codes, units, medications and diseases are protected; product lots and device identifiers are pseudonymized; identifiers, faces and barcodes are masked. PNG/TIFF preserve unmasked pixels exactly, while JPEG retains codec loss.
- Metadata and hidden surfaces require coverage; DOCX drops optional package previews only when they have no other consumer. Saved text, structure and pixels must pass verification before publication.

## Measurements

- Fresh two-CPU/1 GB [local v25](benchmarks/held-in-local-v25.json) published 5/12 in 27.18 s at 803.43 MiB peak; replay changed no bytes or attempts. Hosted measurement is running; adapter availability does not imply all valid files publish.
- The 40-case [development regression](benchmarks/accuracy-v25.json) measured precision 83.78%, recall 79.49%, F1 81.58%, no overlap with 35 labelled clinical spans, and zero false accepts / one false reject in 34 verifier checks; this is not held-out or full-document accuracy.
- **Full 2 GiB acceptance failed:** local v18 ran 11.2 million rows / 2,147,950,662 bytes under two CPUs, a 1 GB limit and no swap; it timed out after 1,800.25 seconds with 1.82 million rows analyzed, zero rewritten or published, approximately 1 GB peak memory and 3.07 GB state. Publication throughput was zero ([record](benchmarks/large-csv-2g-v18.json)).

## Known limitations

- Statistical misses and false positives remain possible; native integration fixtures and the reused development corpus do not establish general clinical accuracy or complete supplied-file acceptance.
- Defaults cap native files at 32 MiB, expanded archives at 256 MiB and aggregate images at 16 million pixels; OCR also limits frames and regions. Unsupported active content, binary payloads, fonts, forms, color modes and pixel types quarantine.
- FHIR birth-bound extensions require downstream interpretation; unsupported formats cannot express every age generalization. Cross-issuer linkage, collision auditing and full-run crash equivalence remain incompletely validated.
- The bulk deadline remains unmet and identity state growth is substantial; replay requires unchanged inputs, runtime and secret, and atomic artifact installation requires one filesystem.
