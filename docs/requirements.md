# Assignment coverage

This records implemented behavior and remaining gaps, not a claim that every
acceptance requirement passes. The latest completed production measurements are
[local v25](../benchmarks/held-in-local-v25.json) and
[hosted v25](../benchmarks/held-in-hosted-v25.json). Both publish five of twelve
supplied files; six valid files and the corrupt file quarantine.

| Requirement | Implemented evidence | Remaining gap |
| --- | --- | --- |
| A1: detect all surviving PHI | Native format inspection, typed fields, contextual patterns, NER, OCR, barcode and face adapters | Full-document recall is not established. Hidden or unsupported structures quarantine; six valid supplied files still fail detection or verification. |
| A2: consistent pseudonyms | Keyed replacements, encrypted identity evidence, patient/provider separation, corroborated identity matching | Cross-issuer linkage and surrogate collision auditing are incomplete. Ambiguous identity evidence can prevent publication. |
| A3: valid native output | Writers and independent readers for CSV, text, XLSX, JSON, HL7, FHIR, DOCX, PDF, images and DICOM | Having an adapter does not establish reliable coverage. Production publication is demonstrated only for HL7, JSON, CSV and XLSX in the supplied set. Bounded native parsers reject oversized or unsupported content. |
| A4: independent verification | Saved bytes, native structure, clinical preservation, independent spaCy/Tesseract, fail-closed verdicts | Statistical misses and false positives remain. The labelled text benchmark is small and does not measure complete-file recall. Hosted judging is not implemented. |
| A5: safe operation | Fenced attempts, checkpoints, atomic publication, encrypted model replay, budgets and local fallback | Full-set crash testing covers two actual kill timings, not every possible interruption. Lost endpoint responses can incur repeat charges. Hosted vision is not implemented. |
| A6: reconciliation | Per-file status, reasons, finding counts, timing and model accounting; PHI-free logs | Accounting counts are not an accuracy ground truth. A timeout before reconciliation may leave only durable progress and benchmark diagnostics. |
| A7: resource limits | Fresh constrained supplied-file runs and a measured full-size CSV attempt | The complete 2 GiB CSV has not passed. The v18 attempt timed out after 30 minutes during analysis, with no published output. |
| Healthcare policies | Consistent patient date offsets, 90+ handling, ZIP rules, separate providers, contextual relatives and clinical-preservation checks | Identity ambiguity and statistical detection still limit coverage. Bounded birth-date representations require consumer interpretation. |
| Part B | The design addresses all ten scale questions with explicit assumptions | Petabyte throughput and cost estimates are projections. The implementation does not demonstrate fleet operation or fleet-wide rate limits. |

## Evaluation priorities

PHI removal and verification carry 25%, healthcare correctness 20%, format depth
15%, scalability design 20%, robustness including A7 10%, and cost/accounting 10%.
Published leaks carry more weight than clearly explained quarantines. Held-out
variants carry the same weight as supplied inputs, so fixture-specific exceptions
are not an acceptable fix.

The next implementation work therefore targets shared detection and verifier
correctness alongside measured bulk bottlenecks. Final results must identify the
exact revision, models, limits, costs and remaining failures; smaller runs never
establish the full A7 result.
