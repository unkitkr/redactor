# Assignment coverage

This records implemented behavior and remaining gaps. Final [local v30](../benchmarks/held-in-local-v30.json)
publishes 8/12 supplied files; [hosted v30](../benchmarks/held-in-hosted-v30.json)
publishes 6/12 with remote detection, judging and vision judging enabled (three
hosted runs at adjacent revisions published 5, 3 and 6 of 12; hosted outcomes
vary with endpoint provider routing, and every run stays fail-closed).
The corrupt file quarantines in both modes. The exact default-local
result is committed in `output/`; full supplied-file acceptance is not achieved.

| Requirement | Implemented evidence | Remaining gap |
| --- | --- | --- |
| A1: detect all surviving PHI | Native format inspection, typed fields, contextual patterns, NER, OCR, barcode and face adapters; deterministic facility, labelled-value and name-adjacent identifier findings | Full-document recall is not established. Four supplied files quarantine with verified causes: the corrupt ZIP container; referral_packet.pdf (an all-caps comma-form patient cell is not recognized, so verification refuses to publish); progress_note.txt (the word model tags an ordinary clinical verb as a person in rewritten text, varying with the model build); wristband_photo.jpg (OCR role-mention spans and an all-caps drug tagged as an organization). Hidden or unsupported structures quarantine. |
| A2: consistent pseudonyms | Keyed replacements, encrypted identity evidence, patient/provider separation, corroborated identity matching, batched anchor probes | Cross-issuer linkage and surrogate collision auditing are incomplete. Ambiguous identity evidence can prevent publication. |
| A3: valid native output | Writers and independent readers for CSV, text, XLSX, JSON, HL7, FHIR, DOCX, PDF, images and DICOM; overlapping PDF redaction rows merge; one-word name mentions keep one-word surrogates | Having an adapter does not establish reliable coverage. Production publication is demonstrated for HL7, JSON, CSV, XLSX, DOCX, FHIR, DICOM and text in the supplied set; the referral PDF quarantines at verification and the wristband photo at verification. Bounded native parsers reject oversized or unsupported content. |
| A4: independent verification | Saved bytes, native structure, clinical preservation, independent spaCy/Tesseract, fail-closed verdicts; hosted judging of saved-output evidence (text and vision) that can only add failures | Statistical misses and false positives remain. The labelled text benchmark is small and does not measure complete-file recall. Judge false-positive behaviour is observed in the hosted run, not a labelled corpus. |
| A5: safe operation | Fenced attempts, checkpoints, atomic publication, encrypted model replay, budgets and local fallback; judge and detector share the $3 budget and disable together; two seeded SIGKILL recoveries reproduce identical verdicts and surrogate values | Full-set crash testing covers two demonstrated kill timings, not every possible interruption. The FHIR bundle's embedded PDF serializes with run-varying internal ordering (equal extracted text), so byte-level equality across crashes does not hold for that one file. Lost endpoint responses can incur repeat charges. Hosted vision detection is not integrated (judging has vision). |
| A6: reconciliation | Per-file status, reasons, finding counts, timing, model accounting and judge degradation codes; PHI-free logs | Accounting counts are not an accuracy ground truth. |
| A7: resource limits | Fresh constrained supplied-file runs, a complete 100,000-row publication at 120.29 s (831 rows/s), and a measured full-size timed attempt | The complete 2 GiB CSV does not finish within 30 minutes. The timed attempt analyzed 1.87M of 11.2M rows in 1800 s; completing the file is projected at roughly four hours and 19 GB of state from the measured rate, and the full-coverage run was stopped rather than waited out. Peak memory stays inside 1 GB with zero OOM kills. Per-row encrypted identity state and single-task analysis limit full-scale speed. |
| Healthcare policies | Consistent patient date offsets, 90+ handling, ZIP rules, separate providers, contextual relatives, clinical scales, software attribution and clinical-preservation checks | Identity ambiguity and statistical detection still limit coverage. Clinical grammars do not establish full terminology-code/display validity. Bounded birth-date representations require consumer interpretation. |
| Part B | The design addresses all ten scale questions with explicit assumptions and measured A7 numbers | Petabyte throughput and cost estimates are projections. The implementation does not demonstrate fleet operation or fleet-wide rate limits. |

## Evaluation priorities

PHI removal and verification carry 25%, healthcare correctness 20%, format depth
15%, scalability design 20%, robustness including A7 10%, and cost/accounting 10%.
Published leaks carry more weight than clearly explained quarantines. Held-out
variants carry the same weight as supplied inputs, so fixture-specific exceptions
are not an acceptable fix.

Measurements identify source, models, resource limits and costs. The 100,000-row
v30 run completed every record in 120.29 s with zero remote calls. On the labelled
40-case corpus, [accuracy v30](../benchmarks/accuracy-v30.json) records precision
86.11%, recall 79.49%, zero labelled clinical overlaps and zero verifier false
accepts or rejects; it does not measure the native-format failure modes fixed
today. Crash recovery evidence is [crash-replay-v30](../benchmarks/crash-replay-v30.json).
There is no new full-document labelled accuracy corpus.
