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
Hosted judging and vision extraction are not integrated.

## Results

Outputs appear beside the state directory: `published/`, `quarantine/`,
`report.json`, `run.log`. Quarantine retains original sensitive files.
The dashboard starts at <http://127.0.0.1:8765>; disable with `--no-dashboard`.

Fresh v28 containers used **2 CPUs, 1,000,000,000 bytes RAM and no extra swap**.
The supplied 12 files are development fixtures, not held-out accuracy data.

| Measurement | Local | Hosted |
| --- | ---: | ---: |
| Published / quarantined | 6 / 6 | 5 / 7 |
| Elapsed | 21.32 s | 408.58 s |
| Peak memory | 801.74 MiB | 802.29 MiB |
| Endpoint attempts / recorded cost | 0 / $0 | 121 / $0.0215 |

[`output/`](output/) contains the exact local result. DOCX now publishes locally;
five valid files still quarantine, plus the corrupt file. Both replays preserved
all bytes and added no attempts. [Local](benchmarks/held-in-local-v28.json) ·
[Hosted](benchmarks/held-in-hosted-v28.json) · [SIGKILL recovery](benchmarks/crash-replay-v28.json).

The [100,000-row run](benchmarks/bulk-100k-v29.json) published every row in 286.56 s
with zero remote calls. **A7 remains failed:** the complete 2 GiB attempt timed out
after 30 minutes. [Full-size evidence](benchmarks/large-csv-2g-v18.json).

[Design](DESIGN.md) · [Decisions and limitations](notes.md) ·
[Requirement coverage](docs/requirements.md) · [Accuracy](benchmarks/accuracy-v28.json)
