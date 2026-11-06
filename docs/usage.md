# Usage reference

## Set up

Run these commands from the project root on Linux or macOS with
[uv](https://docs.astral.sh/uv/) installed:

```bash
uv sync --locked
uv run --locked python tools/benchmarks/fetch_models.py
```


The first command installs Python dependencies and the packaged spaCy model. The
second downloads pinned model artifacts into `.models/`, checks their sizes and
SHA-256 hashes, and skips matching files. It fetches the full benchmark model set,
including alternatives to the selected GLiNER PII Edge UINT8 model. Setup requires
internet access; local inference never downloads missing weights at runtime.

Put the supplied assignment files in `input/`. Inputs and downloaded weights are
excluded from Git.

Create a private environment file **once**, then retain it with your run state:

```bash
uv run --locked --offline python tools/init_environment.py
```

This refuses to overwrite an existing `.env.local` and does not print the secret.
The file is gitignored. If it already exists, keep its key rather than generating a
new one. Losing or changing the key prevents replay of its encrypted state.

## Run the whole pipeline

```bash
uv run --locked --offline --env-file .env.local redactor \
  --input input \
  --state tmp/held-in/.redactor \
  --workers 2
```

This starts the complete pipeline; files that fail an earlier check go directly to
quarantine. One worker handles inference and another handles lighter work.
The command waits for all files to reach publication or quarantine
and then writes the final report. Local processing is the default in both
`redactor.toml` and the settings schema; `.env.local` also explicitly sets
`LLM_ENABLED=0`. uv's `--offline` flag prevents dependency downloads, independently
of whether the pipeline may contact a model endpoint.

Inside the project environment, `python -m redactor` is an equivalent entry point.
The optional `--state` defaults
to `.redactor`; the example uses a separate workspace so earlier runs stay intact.
Configuration comes from `redactor.toml`, or from `--config path/to/config.toml`.
Environment files are loaded explicitly by uv, not automatically by Redactor.

A zero exit code means the inventory was reconciled, **not that every file was
redacted successfully**. Check the published/quarantined counts and reasons.

### Optional hosted detection

To enable hosted detection, create a separate private environment file such as
`.env.hosted`, retaining the same `REDACTOR_SECRET_KEY` for replay. Set
`LLM_ENABLED=1` and supply the endpoint credential as `LLM_API_KEY`. Keep this file
out of Git and readable only by its owner, as with `.env.local`.

```bash
uv run --locked --offline --env-file .env.hosted redactor \
  --input input \
  --state tmp/hosted/.redactor \
  --workers 2
```

| Variable | Purpose |
| --- | --- |
| `LLM_ENABLED` | `1` permits hosted detection; `0` prevents new endpoint calls. |
| `LLM_API_KEY` | Credential for the configured endpoint. |
| `LLM_BASE_URL` | Optional override for the configured OpenAI-compatible endpoint. |
| `LLM_MODEL` | Optional override for the configured model name. |

The checked-in endpoint and model are OpenRouter and `z-ai/glm-5.3-flash`.
An existing variable named `OPENROUTER_KEY` is not read automatically; supply its
value through `LLM_API_KEY`. Redactor does not load `.env` files itself.
Changing the endpoint or model also requires reviewing the provider and pricing
settings in TOML and using a fresh workspace.

Hosted detection runs during analysis of eligible free text. Its validated
observations, including actual local fallback results, are encrypted and saved
before use; rewriting reuses them without another endpoint call. Verification
reconstructs the expected edits from this evidence, then independently checks the
original and saved text with local NER and deterministic rules. Remote judging and hosted vision are not integrated. Native images and embedded
images use local OCR in either mode.

The current configuration allows three attempts per request, including the first,
with exponential backoff, a 30-second attempt timeout and a 65-second request
deadline. Slow responses, rate limits, malformed answers, authentication failures
and exhausted budgets lead to bounded local fallback; failed local inference still
prevents publication. The run budget is $3, with OpenRouter provider price caps of
$0.15 per million input tokens and $0.50 per million output tokens. These are
configured limits, not a promise that every request or file will succeed.

## Inspect and use the results

For the local command above, results appear in `tmp/held-in/output/`; the hosted
example uses `tmp/hosted/output/`:

| Path | Contents |
| --- | --- |
| `published/` | Files accepted by the saved-output verifier, retaining their relative names. |
| `quarantine/` | Original files withheld from publication, with `.reason.json` sidecars. These still contain the original sensitive data. |
| `report.json` | Run completion, per-file outcomes, reason codes, hashes, counts, timings and model usage. |
| `run.log` | The same per-file report entries as newline-delimited JSON. |

The state directory contains SQLite, encrypted identity/model evidence and private
intermediate artifacts. Keep it private. Share only appropriate published outputs
and aggregate reports, not quarantine files or runtime state.

The dashboard starts automatically at <http://127.0.0.1:8765> while the pipeline
runs. It shows durable queue state and HTML views of the JSON benchmarks. Use
`--no-dashboard` to disable it or `--dashboard-port 8766` to change its port.
A dashboard startup failure does not stop processing.

To inspect a completed run, start the dashboard separately:

```bash
uv run --locked --offline redactor-dashboard --state tmp/held-in/.redactor
```

Queue snapshots refresh every five seconds while visible. Benchmark snapshots are
cached for 30 seconds. A running task is a database claim, not a worker heartbeat.
The dashboard is a local, read-only tool without authentication or external assets.

The OCR benchmark gallery contains 12 variants of three reference documents. If
those generated images are absent, recreate them with:

```bash
uv run --locked --offline python tools/make_ocr_corpus.py
```

The gallery appears only when its manifest matches the measured corpus. OCR scores
measure transcription and localization, not safe redacted-image publication.

## Resume a run

Re-run the exact pipeline command with the same inputs, configuration, weights,
secret and input/state locations. Completed steps are reused; interrupted steps recover
from their durable state. Do not delete SQLite journal files or the run lock.
After SIGKILL, let surviving workers exit before restarting the coordinator.

`LLM_ENABLED` may change during recovery. Saved observations and accepted remote
answers still replay with hosted access disabled or its API key absent; the switch
prevents new calls, rather than discarding work already accepted. A crash after an
endpoint responds but before its answer is saved can still require another request
and charge. Keep the original endpoint, model and other processing settings for
the same run.

Outputs belong to one inventory, configuration, secret identity and pipeline
version. Changed inputs or processing choices require a fresh workspace, for
example `--state tmp/another-run/.redactor`. Conflicting outputs produce
`output_content_conflict`; they are never silently overwritten. State and outputs
must share a local filesystem for atomic publication.


## Run in a constrained container

After staging the local weights and secret, build the image:

```bash
docker build -t redactor:local .
docker volume create redactor-state
docker run --name redactor-local \
  --cpus 2 --memory 1000000000 --memory-swap 1000000000 --network none \
  --env-file .env.local \
  --mount type=bind,src="$PWD/input",dst=/work/input,readonly \
  --mount type=bind,src="$PWD/.models",dst=/work/.models,readonly \
  --mount type=bind,src="$PWD/redactor.toml",dst=/work/redactor.toml,readonly \
  --mount type=volume,src=redactor-state,dst=/work/run \
  redactor:local --input input --state run/.redactor --workers 2 --no-dashboard
```

The build needs internet access; this local-only run has no network access and no
extra swap. Keep SQLite state and outputs on the Docker volume: macOS bind-mounted
state produced `SQLITE_CORRUPT` in this evaluation, while native container storage
completed the run and replay ([storage observation](../benchmarks/docker-bind-mount-observation.json)).
The precise filesystem mechanism was not diagnosed. Inputs and weights can remain
read-only bind mounts.

Copy the outputs out after completion, or replay the same retained container:

```bash
mkdir -p tmp/container-run
docker cp redactor-local:/work/run/output tmp/container-run/
docker start --attach redactor-local
```

Use a new container name and volume for a different run. The automatic dashboard
binds the container's loopback, so publishing a host port alone would not expose
it; this container example disables it. The host command above enables the local
dashboard without Docker networking.

## Development

The package supports Python 3.11 and later; `.python-version` selects 3.14 for local
development and the Dockerfile uses 3.12. Workers are separate processes and do not
share one GIL. Select `.venv/bin/python` in the editor.

```bash
uv run --locked --offline ruff check .
uv run --locked --offline ruff format --check .
uv run --locked --offline mypy src tests
uv run --locked --offline pytest -q
```

| Location | Responsibility |
| --- | --- |
| `src/redactor/coordinator/` | Startup, inventory, recovery ownership and worker supervision. |
| `src/redactor/workers/` | Composable pipeline steps and their dispatch. |
| `src/redactor/persistence/` | Queue, checkpoints, artifacts, identities and model accounting. |
| `src/redactor/formats/`, `policy/`, `verification/` | Parsing, transformation rules and independent saved-output checks. |
| `src/redactor/inference/`, `agents/` | Shared local adapters and remote detector prompts/runtime. |
| `src/redactor/schemas/`, `utils/` | Typed contracts, configuration, constants and shared helpers. |
| `src/redactor/migrations/` | Numbered SQL migrations, applied transactionally at startup. |
| `src/redactor/monitoring/` | Read-only HTTP dashboard and plain HTML/CSS/JavaScript. |
| `tools/`, `benchmarks/`, `tests/` | Reproducible measurements, evidence and integration tests. |

SQLite uses WAL, short transactions and `synchronous=FULL`; writes still serialize.
Worker APIs are functional, and step completion commits its result and successors
together. Artifact bytes are persisted before their database references. A saved
verification verdict is bound to the exact output, source and identity snapshot
before publication. These boundaries are described in the [architecture notes](../notes.md).
