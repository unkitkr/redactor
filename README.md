# Redactor

A resumable PHI pseudonymization pipeline: inspect, extract, redact, save,
independently verify, then publish. Unsafe or incompletely assessed files quarantine.
Local processing is the default; hosted detection is optional.

## Setup and run

Requires [uv](https://docs.astral.sh/uv/) and Tesseract with English language data.
Put the supplied files in `input/`, then run:

```bash
uv sync --locked
uv run python tools/benchmarks/fetch_models.py
uv run python tools/init_environment.py
uv run --env-file .env.local redactor --input input --state tmp/local/.redactor --workers 2
```

Setup downloads pinned weights and creates a private `.env.local` without replacing
an existing key. Keep that key and the state directory to resume the same run.

For hosted mode, create `.env.hosted` with the same `REDACTOR_SECRET_KEY`,
`LLM_ENABLED=1` and `LLM_API_KEY` set to your OpenRouter key, then run:

```bash
uv run --env-file .env.hosted redactor --input input --state tmp/hosted/.redactor --workers 2
```

Local models: **GLiNER PII Edge UINT8 + PP-OCRv5**. Hosted detector:
**`z-ai/glm-5.3-flash`**, with local fallback. Independent verification uses
**spaCy + Tesseract**, deterministic checks and source/output comparisons.
Hosted judging and vision extraction are not integrated.

## Results

Results go to `tmp/local/output/` or `tmp/hosted/output/`: `published/`,
`quarantine/`, `report.json` and `run.log`. Quarantine retains original sensitive
files. Exit code zero means processing reconciled, not that every file published.
The dashboard starts at <http://127.0.0.1:8765>; disable it with `--no-dashboard`.

The supplied 12 files are development fixtures, not held-out accuracy data.
Fresh production containers used **2 CPUs, 1,000,000,000 bytes RAM, no extra swap**.

| Measurement | Local | Hosted GLM 5.3 Flash |
| --- | ---: | ---: |
| Published / quarantined | 5 / 7 | Running |
| Elapsed | 27.18 s | Running |
| Peak container memory | 803.43 MiB | Running |
| Endpoint requests / receipt cost | 0 / $0 | Running |

The exact local result is committed in [`output/`](output/). Six valid files still
quarantine; the corrupt file correctly fails container validation. Local replay
preserved all output bytes and added no attempts. This does **not** meet full
supplied-file acceptance. [Per-file evidence](benchmarks/held-in-local-v25.json).

The full **2 GiB CSV gate failed**: the previous run timed out after 30 minutes,
with 1.82 million of 11.2 million rows analyzed and none published.
[Measurement](benchmarks/large-csv-2g-v18.json).

[Detailed usage and Docker](docs/usage.md) · [Design](DESIGN.md) ·
[Decisions and limitations](notes.md) · [Accuracy](benchmarks/accuracy-v25.json)
