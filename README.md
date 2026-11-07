# Redactor

A resumable PHI pseudonymization pipeline: inspect, extract, redact, save,
independently verify, then publish. Local mode is the default. Unsafe or
incompletely assessed files quarantine. **This submission does not meet every acceptance gate.**

## Run

Requires [uv](https://docs.astral.sh/uv/) and Tesseract with English data.
Place the supplied files in `input/`:

```bash
uv sync --locked
uv run python tools/benchmarks/fetch_models.py
uv run python tools/init_environment.py
uv run --env-file .env.local redactor --input input --state tmp/local/.redactor --workers 2
```

Keep the generated secret and state to resume with the same command. Model weights
are downloaded separately from Python dependencies. [Docker and configuration](docs/usage.md).

For hosted mode, create `.env.hosted` with the same `REDACTOR_SECRET_KEY`,
`LLM_ENABLED=1` and your OpenRouter `LLM_API_KEY`:

```bash
uv run --env-file .env.hosted redactor --input input --state tmp/hosted/.redactor --workers 2
```

Local detection uses **GLiNER PII Edge UINT8 + PP-OCRv5**; hosted detection uses
**`z-ai/glm-5.3-flash`**. Independent verification uses **spaCy + Tesseract**.
Request/schema/span failures fall back locally; semantic ambiguity can still quarantine.
Hosted mode also judges saved-output evidence with the same model, including
vision judging of saved images; the judge can only add failures, never clear one,
and `LLM_ENABLED=0` disables all remote calls.

## Results

Outputs appear beside the state directory: `published/`, `quarantine/`,
`report.json`, `run.log`. Quarantine retains original sensitive files.
The dashboard starts at <http://127.0.0.1:8765>; disable with `--no-dashboard`.

Fresh v30 containers used **2 CPUs, 1,000,000,000 bytes RAM and no extra swap**.
The supplied 12 files are development fixtures, not held-out accuracy data.

| Measurement | Local | Hosted |
| --- | ---: | ---: |
| Published / quarantined | 8 / 4 | 6 / 6 |
| Elapsed | 36.74 s | 388.19 s |
| Peak memory | 786.2 MiB | 805.6 MiB |
| Endpoint attempts / recorded cost | 0 / $0 | 133 / $0.0207 |

[`output/`](output/) contains the exact local result. Four files still quarantine:
the corrupt container; the referral PDF (an all-caps comma-form patient cell is
not recognized, so verification refuses to publish); the progress note (the
verifier's word model tags an ordinary clinical verb as a person in the
rewritten text, a build-sensitive false positive); and the wristband photo
(OCR role-mention spans and an all-caps drug tagged as an organization).
Hosted publication is unstable run to run: the endpoint serves the same model
from many providers with differing responses, so three hosted runs at adjacent
revisions published 5/12, 3/12 and 6/12. Every hosted run stays fail-closed (the
verifier caught each missed span; the judge degraded safely on bad responses),
but hosted publication counts vary with provider routing.
The replay rerun preserved all bytes in 2.01 s, and two seeded SIGKILL
recoveries reproduced identical verdicts and surrogate values; only the FHIR
bundle's embedded PDF varies in internal serialization between runs, with
equal extracted text. [Local](benchmarks/held-in-local-v30.json) ·
[Hosted](benchmarks/held-in-hosted-v30.json) ·
[SIGKILL recovery](benchmarks/crash-replay-v30.json).

The [100,000-row run](benchmarks/bulk-100k-v30.json) published every row in
120.29 s with zero remote calls, 2.4x faster than the previous committed
measurement. **A7's 30-minute gate is still not met on the full 2 GiB file:**
the timed attempt analyzed 1.87M of 11.2M rows in 1800 s
([evidence](benchmarks/large-csv-2g-v30.json)); at the measured rate,
completing the file is projected at roughly four hours and about 19 GB of
state, so the full-coverage run was stopped and the projection recorded
instead of a completed measurement.
On the labelled 40-case text corpus, [accuracy v30](benchmarks/accuracy-v30.json)
holds precision 86.11% and recall 79.49% with zero clinical overlaps and zero
verifier false accepts or rejects; today's detection fixes target native-format
failures that corpus does not measure, and show up as published-file outcomes.

[Design](DESIGN.md) · [Decisions and limitations](notes.md) ·
[Requirement coverage](docs/requirements.md) · [Accuracy](benchmarks/accuracy-v28.json)
