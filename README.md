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
and then writes the final report. `.env.local` selects local-only processing through
`LLM_ENABLED=0`; uv's `--offline` flag separately prevents dependency downloads.

Inside the project environment, `python -m redactor` is an equivalent entry point.
The optional `--state` defaults
to `.redactor`; the example uses a separate workspace so earlier runs stay intact.
Configuration comes from `redactor.toml`, or from `--config path/to/config.toml`.
Environment files are loaded explicitly by uv, not automatically by Redactor.

A zero exit code means the inventory was reconciled, **not that every file was
redacted successfully**. Check the published/quarantined counts and reasons.

## Inspect and use the results

For the command above, results appear in `tmp/held-in/output/`:

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

Outputs belong to one inventory, configuration, secret identity and pipeline
version. Changed inputs or processing choices require a fresh workspace, for
example `--state tmp/another-run/.redactor`. Conflicting outputs produce
`output_content_conflict`; they are never silently overwritten. State and outputs
must share a local filesystem for atomic publication.

## Supplied held-in dataset results

The supplied `input/` files are development fixtures, not an independent held-out
accuracy dataset. The measured end-to-end results are recorded in
[the held-in run report](benchmarks/held-in-pipeline.json).

The local-only run reconciled all 12 files, but **published none**. Five files
failed coverage checks, six used unsupported native formats, and one was corrupt.
This demonstrates completion and replay of quarantine outcomes, not successful
redaction of this dataset or full assignment coverage.

| Local-only run | Measured result |
| --- | --- |
| Model | GLiNER PII Edge v1.0 UINT8; external calls disabled |
| Input | 12 files, 533,410 bytes |
| Published / quarantined | 0 / 12 |
| Initial elapsed time | 2.624 seconds |
| Exact-command replay | 1.085 seconds |
| Peak container memory | 572.86 MiB, including probe, coordinator, workers and dashboard |
| Limits | 2 vCPUs, 1 GiB RAM, no extra swap, no network |
| Durable work | 37 completed tasks; replay added no attempts |
| Replay checks | All output bytes and the report unchanged; inputs unchanged |
| Model requests / charges | 0 / $0 |

The dashboard was enabled and reachable. Current source and staged weights were
mounted into the existing evaluation image; this was not a fresh production-image
build. All files branched to quarantine before rewriting and saved-output
verification, so elapsed time measures quarantine processing, not redaction
throughput. The replay was a normal completed-run replay, not a random-SIGKILL test.

All files below were quarantined:

| Supplied file | Detected type | Reason |
| --- | --- | --- |
| `encounters.csv` | CSV | Incomplete coverage |
| `billing_export.csv` | XLSX | Incomplete coverage |
| `patient_roster.xlsx` | XLSX | Incomplete coverage |
| `progress_note.txt` | Text | Incomplete coverage |
| `adt_a01.hl7` | HL7 | Incomplete coverage |
| `claims.json` | JSON | Unsupported native format |
| `fhir_bundle.json` | FHIR | Unsupported native format |
| `discharge_summary.docx` | DOCX | Unsupported native format |
| `referral_packet.pdf` | PDF | Unsupported native format |
| `wristband_photo.jpg` | JPEG | Unsupported native format |
| `imaging_0042.dat` | DICOM | Unsupported native format |
| `corrupt_upload.docx` | ZIP | Invalid container structure |

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

The remote detector helper supports encrypted replay, bounded exponential backoff,
cost limits and local fallback, tested separately from file publication. A failed
local fallback still prevents publication. Production workers currently call local NER
directly; hosted detection and remote judging are not integrated into publication.
Setting `LLM_ENABLED=1` alone therefore does not make this a hosted-model run.

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
