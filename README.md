# Redactor

Redactor is a local PHI pseudonymization pipeline with a durable SQLite queue,
consistent identity mapping, and verification of saved outputs before publication.
It runs inspection, analysis, rewriting, verification and reporting from one command.
Files that cannot be assessed safely are quarantined with a reason.

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
uv run --locked --offline python - <<'PY'
import base64
import os

secret = base64.b64encode(os.urandom(32)).decode()
descriptor = os.open('.env.local', os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
with os.fdopen(descriptor, 'w') as environment:
    environment.write(f'REDACTOR_SECRET_KEY={secret}\nLLM_ENABLED=0\n')
print('Created .env.local; retain it for replay.')
PY
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
original and saved text with local NER and deterministic rules. Remote judging is
not integrated, and enabling hosted mode does not enable image publication.

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

## Supplied held-in dataset results

The supplied `input/` files are development fixtures, not an independent held-out
accuracy dataset. Both modes were run on the same 12 files (533,410 bytes), with
GLiNER PII Edge v1.0 UINT8 available locally, two workers and the dashboard enabled.

**Both modes published zero files.** These runs demonstrate actual model routing,
quarantine accounting and replay, but do not establish successful redaction of the
supplied dataset or full assignment coverage.

| Measurement | [Local default](benchmarks/held-in-local.json) | [Hosted opt-in](benchmarks/held-in-hosted.json) |
| --- | ---: | ---: |
| Hosted model | Disabled | `z-ai/glm-5.3-flash` through OpenRouter |
| Published / quarantined | 0 / 12 | 0 / 12 |
| Initial elapsed time | 11.884 seconds | 80.460 seconds |
| Exact-command replay | 4.922 seconds | 3.682 seconds |
| Peak container memory | 645.72 MiB | 654.48 MiB |
| Completed tasks | 37 | 39 |
| Endpoint requests | 0 | 15 |
| Input / output tokens | 0 / 0 | 6,905 / 6,781 |
| Accounted cost bound | $0 | $0.00442625 |
| Endpoint-reported receipt cost | $0 | $0.003684328 |
| Additional task/model attempts on replay | 0 / 0 | 0 / 0 |

Both containers had 2 vCPUs, 1 GiB RAM and no extra swap. Local mode had no network;
hosted mode used an isolated Docker network with an opaque TLS relay to a fixed
OpenRouter endpoint IP. The client still validated the `openrouter.ai` certificate;
a network probe confirmed the endpoint was reachable and an unrelated site was
blocked. State and outputs used native Linux storage. Memory includes the probe,
coordinator, workers and dashboard. A separate large CSV benchmark ran on the same
Docker host, so these are observed durations, not an isolated latency comparison.

The hosted endpoint returned `z-ai/glm-5.3-flash` for all 15 requests across nine
providers, recorded in the JSON. Eleven unique detector inputs used accepted remote
observations; four fell back locally because three responses were invalid and one
had ungrounded spans. Requests were made during analysis only. Both replays kept
all output/report bytes unchanged, preserved inputs, and made no new model calls.

Local mode quarantined every file before rewriting. Hosted mode rewrote the
mislabeled workbook, but the independent saved-output verifier rejected it with
`residual_phi_detected`. Without full reference labels, that rejection is not
evidence that the file leaked. A [follow-up diagnostic](benchmarks/verifier-metadata-diagnostic.json)
reconstructed the exact staged bytes and traced the rejection to GLiNER
misclassifying an unchanged sheet title as contact information; a new synthetic
title reproduced the same kind of false rejection. This isolates that failure,
not whole-file cleanliness. The remaining files did not reach rewriting. Neither
duration is successful redaction throughput, and these completed-run replays are
not random-SIGKILL tests.

| Supplied file | Detected type | Local quarantine reason | Hosted quarantine reason |
| --- | --- | --- | --- |
| `encounters.csv` | CSV | Incomplete coverage | Incomplete coverage |
| `billing_export.csv` | XLSX | Incomplete coverage | Residual PHI check failed |
| `patient_roster.xlsx` | XLSX | Incomplete coverage | Incomplete coverage |
| `progress_note.txt` | Text | Incomplete coverage | Incomplete coverage |
| `adt_a01.hl7` | HL7 | Incomplete coverage | Incomplete coverage |
| `claims.json` | JSON | Unsupported native format | Unsupported native format |
| `fhir_bundle.json` | FHIR | Unsupported native format | Unsupported native format |
| `discharge_summary.docx` | DOCX | Unsupported native format | Unsupported native format |
| `referral_packet.pdf` | PDF | Unsupported native format | Unsupported native format |
| `wristband_photo.jpg` | JPEG | Unsupported native format | Unsupported native format |
| `imaging_0042.dat` | DICOM | Unsupported native format | Unsupported native format |
| `corrupt_upload.docx` | ZIP | Invalid container structure | Invalid container structure |

These measurements used production revision `7025ae5` mounted into the existing
evaluation image, rather than a fresh production-image build. The records include
exact source, configuration and model hashes. The earlier local-only measurement
is retained as a [historical record](benchmarks/held-in-pipeline.json).

## Generate a large CSV

The assignment generator streams to disk and includes quoted multiline records:

```bash
mkdir -p tmp/large-csv/input
uv run --locked --offline python tools/make_large_csv.py \
  --size-gb 1 --seed 1 --out tmp/large-csv/input/big_encounters.csv
```

The generated file contains **5,600,000 rows and 1,073,957,724 bytes**. The generator
uses GiB units and stops at a 5,000-row boundary, so it slightly exceeds 1 GiB.
An independent CSV parse verified all row widths and found 1,398,979 multiline
records ([generation record](benchmarks/large-csv-1g-generation.json)). Bulk data and
private state stay outside Git. Generating and parsing the fixture alone does not
satisfy the pipeline's large-file acceptance test.

The [1 GiB baseline diagnostic](benchmarks/large-csv-1g.json) **failed** after
929.256 seconds with `worker_failed`. It saved analysis checkpoints for
1,290,000 rows (23.04%), rewrote and published zero rows, and produced no final run
report. Its SQLite state reached 2,178,838,528 bytes. The cgroup reported peak memory
of 1,073,745,920 bytes against a 1 GiB configured limit; the failure cause and an OOM
kill are unconfirmed because the original probe did not retain the final memory
event counters or worker exception category.

That run used frozen production revision `450fdf8`, before the hosted integration.
Production/configuration files matched that revision afterward, but a shared
measurement helper changed on disk during execution, invalidating the combined
unchanged-source fingerprint. It is retained as a failed diagnostic, not a current
acceptance result. No complete-file redaction throughput or 2 GiB acceptance claim
is established. The probe now records memory events and checks that workers have
released run ownership before collecting its final snapshot.

## Models and current coverage

The checked-in configuration selects **GLiNER PII Edge UINT8** for local NER,
**PP-OCRv5 mobile English** for OCR, and **z-ai/glm-5.3-flash** for hosted text.
The [model comparison](benchmarks/README.md) records exact artifacts, accuracy,
latency, memory and historical hosted costs.

Current publication paths cover supported CSV/TSV, labelled text, XLSX and HL7 ADT.
Other formats and unsupported document features quarantine. GLiNER can also reject
otherwise valid supported files when safe coverage cannot be established. To use
the established spaCy path explicitly, create a separate configuration:

```toml
[local]
ner = "spacy"

[remote]
enabled = false
```

Pass it through `--config` and use a fresh output workspace. Tesseract and PP-OCR
share bounded OCR adapters but do not yet enable image publication. Tesseract also
requires its system executable and local English trained data.

Hosted detection is integrated into analysis for the supported publication paths,
with encrypted observation replay, bounded backoff, cost limits and local fallback.
It remains opt-in and requires endpoint credentials; it does not expand native
format support or bypass the independent saved-output verifier. Remote judging
remains unimplemented in the publication pipeline.

The [decision log](notes.md) separates selected policies, measured evidence and
known limitations. Neither the small fixture run nor the model benchmarks establish
clinical safety or satisfy the 2 GiB CSV / 30-minute acceptance target. Full-run
random-SIGKILL equivalence remains unvalidated.

## Run in a constrained container

After staging the local weights and secret, build the image:

```bash
docker build -t redactor:local .
docker volume create redactor-state
docker run --name redactor-local \
  --cpus 2 --memory 1g --memory-swap 1g --network none \
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
completed the run and replay ([storage observation](benchmarks/docker-bind-mount-observation.json)).
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
before publication. These boundaries are described in the [architecture notes](notes.md).
