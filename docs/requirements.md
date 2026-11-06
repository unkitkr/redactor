# Assignment coverage

This records implemented behavior and remaining gaps. Final [local v28](../benchmarks/held-in-local-v28.json)
publishes 6/12 supplied files; [hosted v28](../benchmarks/held-in-hosted-v28.json)
publishes 5/12. The corrupt file quarantines in both modes. The exact default-local
result is committed in `output/`; full supplied-file acceptance is not achieved.

| Requirement | Implemented evidence | Remaining gap |
| --- | --- | --- |
| A1: detect all surviving PHI | Native format inspection, typed fields, contextual patterns, NER, OCR, barcode and face adapters | Full-document recall is not established. Hidden or unsupported structures quarantine; five valid supplied files locally still fail detection or verification. |
| A2: consistent pseudonyms | Keyed replacements, encrypted identity evidence, patient/provider separation, corroborated identity matching | Cross-issuer linkage and surrogate collision auditing are incomplete. Ambiguous identity evidence can prevent publication. |
| A3: valid native output | Writers and independent readers for CSV, text, XLSX, JSON, HL7, FHIR, DOCX, PDF, images and DICOM | Having an adapter does not establish reliable coverage. Production publication is demonstrated for HL7, JSON, CSV, XLSX and DOCX in the supplied set. Bounded native parsers reject oversized or unsupported content. |
| A4: independent verification | Saved bytes, native structure, clinical preservation, independent spaCy/Tesseract, fail-closed verdicts | Statistical misses and false positives remain. The labelled text benchmark is small and does not measure complete-file recall. Hosted judging is not implemented. |
| A5: safe operation | Fenced attempts, checkpoints, atomic publication, encrypted model replay, budgets and local fallback | Full-set crash testing covers two actual kill timings, not every possible interruption. Lost endpoint responses can incur repeat charges. Hosted vision is not implemented. Fallback covers request/schema/span errors, not every semantic classification failure. |
| A6: reconciliation | Per-file status, reasons, finding counts, timing and model accounting; PHI-free logs | Accounting counts are not an accuracy ground truth. A timeout before reconciliation may leave only durable progress and benchmark diagnostics. |
| A7: resource limits | Fresh constrained supplied-file runs, a complete 100,000-row publication and a measured full-size CSV attempt | The complete 2 GiB CSV has not passed. The v18 attempt timed out after 30 minutes during analysis, with no published output. Complete verification and repeated inference remain bottlenecks. |
| Healthcare policies | Consistent patient date offsets, 90+ handling, ZIP rules, separate providers, contextual relatives and clinical-preservation checks | Identity ambiguity and statistical detection still limit coverage. Clinical grammars do not establish full terminology-code/display validity. Bounded birth-date representations require consumer interpretation. |
| Part B | The design addresses all ten scale questions with explicit assumptions | Petabyte throughput and cost estimates are projections. The implementation does not demonstrate fleet operation or fleet-wide rate limits. |

## Evaluation priorities

PHI removal and verification carry 25%, healthcare correctness 20%, format depth
15%, scalability design 20%, robustness including A7 10%, and cost/accounting 10%.
Published leaks carry more weight than clearly explained quarantines. Held-out
variants carry the same weight as supplied inputs, so fixture-specific exceptions
are not an acceptable fix.

Measurements identify source, models, resource limits and costs. The 100,000-row
run completed every record but does not establish the full A7 result. Final local
replay and two SIGKILL recoveries preserved artifact bytes; the initial crash probe's
lock-release timing issue and its corrected rerun are both retained. Hosted egress
used a Docker bridge; an endpoint-only network restriction was not enforced in that
measurement. There is no new full-document labelled accuracy corpus.
