# Direct-function experiment

Run the same native readers, redaction rules and independent saved-output checks
without the coordinator, workers, SQLite, checkpoints or durable model replay.
This isolates execution overhead from content-processing failures.

From the repository root, after the normal model and environment setup:

```bash
uv run --env-file .env.local python -m simple_pipeline.run \
  --input input --output tmp/simple-run
```

The output directory must be new. This runner always uses local models, even if
the shared TOML enables hosted calls. Inputs remain unchanged. Verified files go
to `published/`; failures produce reason JSON in `quarantine/`. `report.json`
records each outcome and stage timing. Failed candidates are removed.

`run.py` calls extraction and detection, resolves identities in memory, then calls
redaction, saving and verification. Detection findings are reused directly.
Verification reopens the saved file, checks its native structure and pixels,
recomputes typed transformations and independently scans text with spaCy.

This is a small-corpus experiment: at most 100 files, 32 MiB of total input and
10,000 extracted records across accepted files, plus the existing native parser
limits. Excess inputs are rejected, never sampled. All evidence is in memory.
There is no crash recovery, streaming bulk path, hosted mode or A7 claim.
It reuses the existing detection and verification logic, so it is not a test of
a new model or a new redaction policy.
