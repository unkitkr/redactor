## Architecture

- One command reads input/, decides what each file really is from its content, removes identifiers, writes the same format back, checks the saved bytes independently, then publishes or quarantines with a machine-readable reason.
- An SQLite ledger, record-boundary checkpoints, encrypted evidence and atomic writes make runs resumable; a killed run resumes without double work or half-written files.
- Local mode is the default and makes no network calls. Hosted mode adds a remote detector and a remote judge that reviews saved-output evidence; both share one $3 budget, with retries, replay and local fallback.
- Verification never trusts the detector: saved files are reopened, structure is rechecked, edits are recomputed, and a separate model scans the text again. A judge can only add failures; it can never clear a failed check.
- A separate [direct-function experiment](simple_pipeline/) runs the same readers and checks without the durable machinery; it is a diagnostic, with no recovery or bulk guarantees.

## Stack

- GLiNER PII Edge UINT8 and PP-OCRv5 detect; spaCy and Tesseract verify independently; ZXing-C++ reads barcodes and YuNet finds faces.
- Optional GLM 5.3 Flash (text detection, plus text and vision judging) with encrypted replay and cost accounting; Python, Pydantic, TOML and AES-GCM; PyMuPDF, pydicom, lxml and openpyxl parse native formats.

## Choices

- File content decides the format, not the file name or extension.
- Two mentions are the same person only when evidence corroborates it; a shared name alone never merges two people. Providers keep their own namespace and never receive patient pseudonyms.
- Each patient's dates shift by one constant offset, so intervals survive across files and notations. A date that cannot be tied to a patient keeps a stable per-context offset.
- Ages of 90 and above become 90+. ZIP codes keep three digits, or 000 for restricted prefixes. Smaller places, device identifiers and lot numbers get stable pseudonyms.
- Clinical codes, lab values, units, medications and disease names are never touched. Standard clinical scales (Hoehn and Yahr, NYHA and similar) and software attribution strings count as clinical content, not identifiers.
- A bare run of six or more digits beside a person's name is treated as that person's identifier; a genuine quantity in that position would be pseudonymized too, which is accepted to close a real leak.
- DICOM private creator tags are pseudonymized as vendor identifiers.
- Pixel PHI is masked, not redrawn; PNG and TIFF keep other pixels exactly, JPEG keeps its normal compression loss.

## Measurements

- Two CPUs / 1 GB / no swap: local mode published 8 of 12 supplied files in 36.74 s ([evidence](benchmarks/held-in-local-v30.json)); hosted mode with judging published 6 of 12 in 388.19 s with 133 receipts and $0.0207 recorded ([evidence](benchmarks/held-in-hosted-v30.json)). Hosted publication varies run to run (three runs published 5, 3 and 6 of 12) because the endpoint serves the model from many providers with differing responses; every run stays fail-closed.
- 100,000-row CSV, same limits, model disabled: 120.29 s, every row published, 831 rows/s, peak memory at the 1 GB ceiling, no out-of-memory kills ([evidence](benchmarks/bulk-100k-v30.json)).
- Full 2 GiB CSV, 11.2M rows: the 30-minute gate was not met. The timed attempt reached 1.87M analyzed rows in 1800 s ([evidence](benchmarks/large-csv-2g-v30.json)); at the measured at-scale rate of about 1,040 analyzed rows/s, completing the file is projected at roughly four hours and about 19 GB of state, so the full-coverage run was stopped and this projection is recorded instead of a completed measurement. Peak memory stayed inside 1 GB with zero out-of-memory kills in every run.
- Labelled 40-case corpus: precision 86.11%, recall 79.49%, zero labelled clinical overlaps, zero verifier false accepts or false rejects ([evidence](benchmarks/accuracy-v30.json)).
- Two seeded SIGKILL recoveries reproduced identical verdicts, counts and surrogate values; every published file matched the clean run byte for byte except the FHIR bundle, whose embedded PDF is written with run-varying internal serialization (extracted text equal), so that file's digest differs between runs ([evidence](benchmarks/crash-replay-v30.json)).

## Requirements

- A1 detect: native inspection, typed fields, contextual patterns, NER, OCR, barcode and face adapters; whole-document recall is not proven.
- A2 pseudonymise: keyed same-value surrogates, corroborated identity matching, separate provider namespace; cross-issuer linkage and collision audits are missing.
- A3 write output: same-format writers and independent readers for CSV, text, XLSX, JSON, HL7, FHIR, DOCX, PDF, images and DICOM; eight supplied files publish.
- A4 verify: saved bytes, structure, clinical preservation and independent spaCy and Tesseract, plus hosted text and vision judging that only adds failures; judge false positives are observed only in hosted runs.
- A5 operate: fenced attempts, checkpoints, atomic publication, encrypted replay and shared budgets; crash coverage is two demonstrated kill points and vision detection is not integrated.
- A6 account: per-file status, reasons, detected/applied/confirmed counts, timing, tokens, cost and judge degradation, with PHI-free logs.
- A7 limits: the 100,000-row file completes inside the container limits; the full 2 GiB gate is not met (see Measurements).
- Healthcare rules: consistent per-patient date offsets, 90+ ages, ZIP rules, provider separation, relatives and preserved clinical codes, values and scales.
- Part B: all ten scale questions are answered with the measured A7 numbers; fleet operation and rate limits remain projections.

## Known limitations

- The A7 30-minute limit on the full 2 GiB file is not met: analysis at full scale runs at about 1,040 rows/s where roughly 6,200 is needed. The causes are per-row encrypted identity state (about 19 GB for 11.2M rows) and single-task analysis that leaves the second CPU mostly idle; fixing either means redesigning the bulk path, which was cut for time.
- Four supplied files still quarantine, each with a verified cause: the corrupt ZIP container (correct); referral_packet.pdf, whose all-caps comma-form patient cell (written LAST, FIRST) is not recognized by known-name matching, so that cell is left unreplaced and verification refuses to publish; progress_note.txt, where the verifier's word model tags an ordinary clinical verb as a person in the rewritten text (a false positive that varies with the word-model build); and wristband_photo.jpg, where an OCR role mention (Dr. NAME ADM) needs a wider exemption than word-level spans and the word model tags the all-caps drug name PENICILLIN as an organization.
- Whole-document recall is not proven; the labelled corpus is small and synthetic.
- Native limits: 32 MiB files, 256 MiB expanded archives and 16 million image pixels; anything unsupported or oversized quarantines.
- Crash coverage is demonstrated kill points, not every possible interruption. Hosted vision detection is not integrated (judging has vision, detection does not). Cross-issuer linkage and surrogate collision audits are not implemented.
- [Requirement coverage](docs/requirements.md) separates demonstrated results from omissions.
