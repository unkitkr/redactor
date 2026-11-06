# Model benchmark results

Measured on 6 November 2026. This comparison covers the research candidates and the GLM family requested in discussion. It does not establish end-to-end pipeline safety or satisfy the 2 GiB CSV acceptance benchmark.

## Conditions and labels

- Text: 40 fixed, manually authored synthetic cases, 39 annotated sensitive mentions, plus explicit clinical spans. The corpus was written before the comparisons and was not tuned to improve a model score. It is a development challenge set, not an independent clinical validation dataset.
- Exact typed-span precision/recall requires the complete annotated boundary and category. Whole-mention coverage and per-type results are also retained in each JSON report. Failed grounding or malformed responses count as abstentions and missed mentions, never as successful empty detection.
- OCR: 12 images from two synthetic cards and the supplied wristband, each tested clean, rotated 5 degrees, blurred, and at reduced contrast. There are 52 identifier targets and 20 clinical targets across the variants. These transformations are correlated examples, not 12 independent documents.
- Local models ran separately on Linux/aarch64 through Docker Desktop with 2 vCPUs, 1 GiB memory, no extra swap, and networking disabled. Peak memory is the cgroup peak, including file cache; timing below excludes model loading. This measures one model process, not the complete worker pool.
- Hosted calls used OpenRouter from the macOS client. The client was not container-constrained; remote server memory is not measurable here. Only synthetic evaluation data was sent. All hosted models used temperature 0, at most two attempts, a 30-second attempt timeout, a 65-second request deadline, structured JSON validation, and the same text prompt. The output limit was 2,048 tokens for text and 4,096 for OCR. These differ from the default pipeline timeout settings. DeepSeek reasoning was disabled; GLM required reasoning enabled.
- Local combined-policy runs use the candidate as residual NER. Hosted combined-policy results use mandatory local spaCy verification. There is no LLM judge in this experiment. Replay rescoring reused the paid responses; its elapsed time is not endpoint latency.

## Text detection

| Candidate | Exact precision | Exact recall | F1 | Clinical spans flagged | Raw detection seconds | Peak local MiB |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| [spaCy en_core_web_sm 3.8.0](results/spacy.json) | 47.4% | 46.2% | 46.8% | 10 | 0.07 | 125.4 |
| [GLiNER PII Edge v1.0 UINT8](results/gliner-edge.json) | 48.2% | 69.2% | 56.8% | 15 | 0.90 | 195.6 |
| [GLiNER PII Small v1.0 UINT8](results/gliner-small.json) | 40.0% | 66.7% | 50.0% | 16 | 1.65 | 274.8 |
| [OpenMed SuperClinical Small INT8](results/openmed.json) | 42.9% | 61.5% | 50.5% | 2 | 0.48 | 1024.0 |
| [deepseek/deepseek-v4.1-flash-1017](results/deepseek-flash.json) | 85.7% | 46.2% | 60.0% | 1 | 58.25 | not measured |
| [deepseek/deepseek-v4-pro](results/deepseek-pro.json) | 86.4% | 48.7% | 62.3% | 0 | 67.77 | not measured |
| [z-ai/glm-5.3-flash](results/glm-flash.json) | 81.8% | 69.2% | 75.0% | 0 | 182.63 | not measured |

Raw NER can over-detect values that the policy later preserves. The clinical column measures overlap with explicitly labelled clinical spans; it is not a count of published changes. The original comparison produced zero such clinical-span edits on this corpus, but still missed identifiers in some accepted cases.

The local exports use pinned tokenizers and checksummed weights from [model-artifacts.json](model-artifacts.json). GLiNER uses a fixed 0.3 threshold and explicit identifier labels, with token-level start/end/inside decoding and no truncation. OpenMed uses its BIO labels, joins adjacent first/last-name components, and trims tokenizer whitespace. The GLiNER decoder matched the upstream `gliner` 0.2.30 wrapper on all 71 Edge and 69 Small inputs, including masked and rewritten text ([parity results](results/gliner-parity.json)). A tied-score ordering discrepancy was corrected before the final measurements. OpenMed uses custom BIO grouping without a separate upstream parity comparison.

NVIDIA `nvidia/gliner-PII` is [excluded by resource preflight](results/nvidia-preflight.json): its published weight file is 1,782,000,995 bytes. No inference or OOM experiment was run, so no accuracy is claimed. OpenMed completed but reached 1 GiB cgroup memory and about 1003 MiB process RSS during loading; that leaves insufficient demonstrated headroom for the full pipeline.

## Original combined policy and verifier

| Detector | Policy abstentions / 40 | Verifier checked | False accepts | False rejects |
| --- | ---: | ---: | ---: | ---: |
| spaCy en_core_web_sm 3.8.0 | 11 | 29 | 2 | 1 |
| GLiNER PII Edge v1.0 UINT8 | 22 | 18 | 0 | 1 |
| GLiNER PII Small v1.0 UINT8 | 20 | 20 | 2 | 1 |
| OpenMed SuperClinical Small INT8 | 14 | 26 | 0 | 1 |
| deepseek/deepseek-v4.1-flash-1017 | 9 | 31 | 2 | 3 |
| deepseek/deepseek-v4-pro | 11 | 29 | 1 | 2 |
| z-ai/glm-5.3-flash | 8 | 32 | 1 | 3 |

A false accept means the text-unit verifier accepted a result with an incompletely covered reference identifier or a changed clinical reference span. These are not full-file publication measurements. Zero false accepts with many abstentions does not establish high recall. Observed escapes include partially handled initialled names, international telephone numbers, and candidate-specific missed names or facilities. These results motivated the verifier changes measured below; the original reports are retained unchanged.

## Verifier v3 regression rerun

The same 40 cases, labels and model weights were rerun after the verifier changes in `74e33e0`. These are regression measurements on a development corpus already inspected during debugging, not independent held-out evidence. Additional adversarial tests use different values and cover omitted names, clinical decoys, Unicode forms, partial phone extensions, CSV headers, XML carriers, ambiguous worksheet cells and unaccounted ZIP bytes; they do not change the benchmark corpus.

| Local detector and residual NER | Policy abstentions / 40 | Verifier checked | False accepts | False rejects | Combined seconds | Peak process MiB |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| [spaCy en_core_web_sm 3.8.0](results/verifier-v3-spacy.json) | 11 | 29 | 0 | 1 | 0.11 | 152.5 |
| [GLiNER PII Edge v1.0 UINT8](results/verifier-v3-gliner-edge.json) | 21 | 19 | 0 | 4 | 1.59 | 252.2 |
| [GLiNER PII Small v1.0 UINT8](results/verifier-v3-gliner-small.json) | 19 | 21 | 0 | 0 | 3.18 | 290.6 |
| [OpenMed SuperClinical Small INT8](results/verifier-v3-openmed.json) | 13 | 27 | 0 | 1 | 0.91 | 890.0 |

These reruns used macOS and Python 3.14.2, with remote models disabled and no container CPU or memory limits. Peak process RSS includes model loading and both evaluation passes; combined time excludes loading. These values do not replace the constrained measurements above or validate A7. Each JSON records the corpus SHA-256, verifier version, revision and environment. The dirty-tree marker reflects generated report files after the code commit.

Raw model precision, recall and F1 were unchanged. The combined policy again made zero edits overlapping the labelled clinical spans. No false accept was observed with any of these four adapters; that does not prove absence of unlabelled or unfamiliar identifiers. The stricter intact-context scan still rejects some safe outputs when a model extends an entity outside an assessed span, particularly GLiNER Edge. Those failures remain quarantines, not silently accepted results.

Verification now checks intact source and saved text, corroborated name variants, independently identified contact values and Unicode-normalized views. Clinical exemptions are tied to source locations, and labelled SNOMED concept identifiers require structural and checksum validation. Native checks account for supported XML names and attributes, every worksheet cell and ZIP member boundary, and unchanged workbook layout and styles. Unsupported Office extensions and international phone formats remain explicit quarantine cases.

Validation at the verifier-v3 milestone: Ruff formatting/lint and mypy passed. The default suite finished with 144 passed and one known CLI failure from the then-unsupported GLiNER production selection. The publish-and-replay CLI test separately passed with explicit spaCy settings, publishing four supported files and quarantining one corrupt input. Output ownership rejects a changed run in an existing output directory, so older publications cannot accompany a newer verification report. No remote judge or saved-image verification is validated here.

The subsequent pipeline-v4 loader integration supports the selected GLiNER export through the same bounded, validated adapter used by evaluation. Its real CLI regression publishes a CSV containing a free-text patient name, preserves clinical content, replays identical bytes and quarantines when weights are missing. The four valid files in the earlier mixed-format regression still quarantine with GLiNER because of unresolved coverage; this is a policy/model compatibility limit, not a loading error. That cross-format regression now explicitly selects spaCy, and the separate GLiNER test exercises the checked-in configuration. The 150-test suite passes; this is integration evidence, not a new accuracy or constrained-container benchmark.

Local OCR now also uses a shared functional loader with locked runtimes, pre-inference image limits, finite source-pixel geometry, and explicit errors for empty or partial outputs. PP-OCR requires local weights with an embedded character dictionary, preventing its dictionary download fallback. Its 12-image English regression retained all earlier per-case accuracy and geometry metrics. Hosted OCR uses the same input and output checks, including on cached responses; those tests use a controlled HTTP transport and incur no model charges. This does not establish pixel verification or image publication.

Loader validation: Ruff, formatting and mypy pass; the full suite has 154 passed and one skipped host Tesseract check. Coverage is 85%. A clean production-only Python environment loads spaCy, GLiNER and PP-OCR. A separate offline smoke check under 2 vCPUs and 1 GiB publishes and replays one CSV and reads one synthetic image with both PP-OCR and Tesseract. That check mounts the current source into the existing evaluation image; a fresh production image build was blocked by the spaCy GitHub wheel download timing out. These are integration checks, not the bulk acceptance benchmark.

### Hosted response replay

The three hosted configurations were also rescored with the new verifier using the existing encrypted `pipeline-v2` response cache and the unchanged corpus. The replay adapter opens SQLite read-only, does not read an API key or construct an HTTP transport, and applies current grounding and policy checks. The raw detection sections are copied from the original reports, identified by SHA-256; they are not fresh model measurements.

| Recorded detector with local spaCy verification | Policy abstentions / 40 | Verifier checked | False accepts | False rejects | Cache misses | Other local fallbacks |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| [deepseek/deepseek-v4.1-flash-1017](results/verifier-v3-deepseek-flash.json) | 10 | 30 | 0 | 2 | 3 | 9 |
| [deepseek/deepseek-v4-pro](results/verifier-v3-deepseek-pro.json) | 10 | 30 | 0 | 2 | 3 | 8 |
| [z-ai/glm-5.3-flash](results/verifier-v3-glm-flash.json) | 9 | 31 | 0 | 2 | 3 | 9 |

Each configuration had 37 cached decisions and three cache misses because current policy produced some detector inputs absent from the historical cache. Other fallbacks came from rejected span evidence or previously recorded model failures. These are mixed replay/local-fallback measurements, not pure hosted-model comparisons. Each reports zero new requests and zero new charges; the shared conservative ledger remains $2.4229058. Replay took 0.25–0.38 seconds per configuration on macOS, which is local evaluation time rather than endpoint latency. No labelled clinical span was edited, and no false accept was observed; each configuration still had two false rejects.

Reproduce a replay without loading `.env`:

```sh
uv run --no-sync python tools/evaluate_remote.py \
  --model z-ai/glm-5.3-flash \
  --previous-result benchmarks/results/glm-flash.json \
  --replay-processing-version pipeline-v2 \
  --output benchmarks/results/verifier-v3-glm-flash.json
```

The private historical ledger and its encryption key are required. Production cache identities and invalidation were not relaxed to enable this evaluation.

## OCR

| Candidate | Identifiers read / 52 | Identifiers localized / 52 | Clinical targets read / 20 | Boxes overlapping clinical targets | Character error rate | Inference seconds | Peak local MiB |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| [Tesseract eng fast](results/tesseract-fast.json) | 41 | 36 | 18 | 1 | 11.2% | 1.65 | 53.1 |
| [Tesseract eng best](results/tesseract-best.json) | 41 | 36 | 18 | 1 | 11.2% | 2.01 | 88.0 |
| [PP-OCRv5 mobile English](results/ppocr-en.json) | 44 | 44 | 20 | 3 | 2.5% | 7.07 | 343.7 |
| [PP-OCRv5 mobile Latin](results/ppocr-latin.json) | 44 | 44 | 20 | 3 | 2.6% | 7.21 | 346.8 |
| [DeepSeek V4.1 Flash 1017 vision](results/deepseek-flash-vision.json) | 45 | 33 | 19 | 0 | 8.5% | 20.85 | not measured |
| [GLM 5.3 Flash vision](results/glm-flash-vision.json) | 32 | 26 | 16 | 0 | 25.4% | 49.84 | not measured |

Localization requires the complete normalized identifier text near its reference box and at least 90% coverage by the enclosing returned boxes. Clinical overlap is scored separately. This is a geometry diagnostic, not proof that every identifying pixel would be removed. Character scoring normalizes case and whitespace; identifier recovery retains punctuation and accents.

Tesseract used the actual CLI with pinned fast/best English data and automatic page segmentation. PP-OCR used RapidOCR 3.10.0, the pinned v5 mobile detector/classifier, and separate English/Latin recognizers with explicit v5 preprocessing. Hosted models returned transcription plus original-pixel coordinates. DeepSeek Pro is text-only and was not sent images.

The vision runs rejected one DeepSeek response and three GLM responses because schema, completion or coordinate checks failed. The image set does not measure handwriting, barcodes, faces, every PDF page, DICOM pixel variants, document metadata, or hidden Office surfaces. No image sanitization or saved-image verifier is claimed.

## Hosted model provenance and cost

Exact requested and returned model IDs, routed providers, token counts, and response costs are recorded in [openrouter-summary.json](results/openrouter-summary.json) and [PHI-free request receipts](results/openrouter-receipts.jsonl). OpenRouter selected multiple providers, so these are routed-model observations rather than controlled single-provider trials.

Successful API receipts report **$0.045215**. The shared durable ledger accounts for **$2.4229058**, below the $3 cap, because it retains conservative reservations for rejected or uncertain requests. One additional diagnostic HTTP 400 response had no usage receipt. Initial GLM requests with reasoning disabled were rejected; [that failure run](results/glm-flash-rejected.json) is retained separately and is not a GLM accuracy measurement.

## Supplied held-in pipeline runs

Both [local](held-in-local.json) and [hosted](held-in-hosted.json) modes processed
the 12 supplied files (533,410 bytes) using production revision `7025ae5`, two
workers, GLiNER PII Edge v1.0 UINT8 and the default dashboard. Both reconciled the
inventory and published **zero files**. These are actual production-path runs,
but not successful de-identification or accuracy measurements.

| Measurement | Local default | Hosted opt-in |
| --- | ---: | ---: |
| Initial seconds | 11.884 | 80.460 |
| Replay seconds | 4.922 | 3.682 |
| Whole-container peak MiB | 645.72 | 654.48 |
| Completed tasks | 37 | 39 |
| Published / quarantined | 0 / 12 | 0 / 12 |
| Endpoint requests | 0 | 15 |
| Input / output tokens | 0 / 0 | 6,905 / 6,781 |
| Accounted cost bound | $0 | $0.00442625 |
| Persisted receipt cost | $0 | $0.003684328 |

The requested and returned hosted model was `z-ai/glm-5.3-flash`; nine routed
providers are identified in the record. Eleven unique detector inputs used remote
observations. Four used local fallback: three invalid responses and one invalid
span grounding. This mixed result is not a pure hosted-model accuracy score.
Saved responses and grounded observations replayed without new calls or charges.

Local mode did not reach rewriting. Hosted mode rewrote `billing_export.csv`
(detected as XLSX), then its independent saved-output verifier rejected it with
`residual_phi_detected`. The other files quarantined for incomplete coverage,
unsupported formats or an invalid container. Full per-file outcomes are in the
[project README](../README.md#supplied-held-in-dataset-results). A later
[metadata diagnostic](verifier-metadata-diagnostic.json) reconstructed the exact
staged artifact and isolated an unchanged sheet title misclassified as contact
information. An unrelated synthetic title reproduced the issue. This identifies
one false rejection, not proof that the complete workbook is clean.

Both containers had 2 vCPUs, 1 GiB RAM and zero extra swap. Local networking was
disabled. Hosted networking used an isolated Docker network with a separate opaque
TLS relay to a fixed OpenRouter endpoint IP, retaining endpoint certificate
validation. A public endpoint probe succeeded while an unrelated HTTPS probe was
blocked. The [relay helper](../tools/benchmarks/endpoint_proxy.py) needs an outbound
network plus the isolated network alias `openrouter.ai`; pipeline containers join
only the isolated network. The relay constrains destination IP and port, not every
possible hostname served by shared CDN infrastructure.

Source, configuration, input and weights were read-only mounts in the existing
evaluation image. State and outputs used native Linux storage. The model, source,
configuration and image fingerprints are retained in each JSON. A separate large
CSV benchmark ran concurrently on the Docker host; these timings are observations,
not an isolated comparison of model latency. The peak includes the coordinator,
workers, probe, dashboard and file cache, but excludes the separate TLS relay.

Both exact-command replays kept every output/report byte and queue count unchanged.
Inputs were unchanged. Neither run injected random crashes or exercised the large
CSV deadline. The [earlier local run](held-in-pipeline.json) is retained unchanged
as historical evidence from revision `6be0224`.

The reusable probe accepts either mode inside a resource-limited Linux container:

```sh
LLM_ENABLED=0 python tools/benchmarks/pipeline.py \
  --mode local --input /work/input --config /work/redactor.toml \
  --state /work/run/.redactor --workers 2 --output /work/run/measurement.json
```

For hosted measurement, use `--mode hosted`, `LLM_ENABLED=1` and `LLM_API_KEY`.
Retain the private mapping key and use a fresh state/output workspace for each
comparison. The probe performs the initial run and replay itself; it requires at
least one real request in hosted mode. The [storage observation](docker-bind-mount-observation.json)
records SQLite errors with macOS bind-mounted state, so use native Linux storage.

## Generated 1 GiB baseline diagnostic

The supplied generator produced 5,600,000 data rows / 1,073,957,724 bytes using
`--size-gb 1 --seed 1`; an independent complete CSV parse validated all row widths
and counted 1,398,979 multiline records ([generation record](large-csv-1g-generation.json)).
The bulk CSV is ignored by Git.

The [pipeline diagnostic](large-csv-1g.json) used two workers and GLiNER, with the
dashboard enabled, external calls disabled, 2 vCPUs, 1 GiB, zero extra swap, no
network and native Linux state storage. It failed after 929.256 seconds, before
its 1,800-second deadline. Stopped-container state confirmed 1,290,000 analyzed
checkpoint rows (23.04%), zero rewritten or published rows, and no final report.
SQLite occupied 2,178,838,528 bytes. There were no model requests or charges.

Peak cgroup memory was 1,073,745,920 bytes. The two retained `worker_failed` codes
do not identify the exception or establish an OOM kill; final memory-event
counters were not captured. All 208 frozen production/configuration files still
matched revision `450fdf8`, but a shared benchmark helper changed on disk during
execution. The combined source fingerprint therefore failed its stability check.
This is an unsuccessful baseline diagnostic, not a final throughput measurement
or an A7 pass. The supplied fixtures were benchmarked in separate containers
during part of this run on the same Docker host.

The [large-file probe](../tools/benchmarks/large_csv.py) now records memory events
and refuses a final snapshot while a surviving worker holds the run lock. A
successful small-file smoke check exercises the probe, not the large-file target.

## Dashboard overhead

The [dashboard measurement](results/dashboard-overhead.json) used 1,000 synthetic queue tasks and 33 benchmark files under 2 vCPUs, 1 GiB memory, no extra swap and no network. The parent-owned server started in 0.284 seconds. Four queue polls over 20 seconds consumed 0.15 CPU seconds, or 0.75% of one core, with mean request latency of 40.33 ms. Idle CPU usage was below the 10 ms clock resolution during a 10-second observation.

Observed server peak RSS was 43.07 MiB; the entire measurement container peaked at 62.93 MiB, including queue seeding and the HTTP client. The first benchmark request took 113.98 ms and a cached request took 4.89 ms. No checked model runtime was imported. These measurements support starting the monitor by default, with `--no-dashboard` available. They exclude browser overhead and concurrent pipeline execution, so they do not measure the effect on pipeline throughput.

The [container receipt](results/dashboard-overhead-container.json) records the image and limits. Current Python and static assets were mounted into the existing evaluation image; the report fingerprints both and confirms they stayed unchanged during the measurement. Prior dashboard reports are excluded from its input set to keep repeated measurements comparable.

```sh
uv run --locked --offline python tools/benchmarks/run_container.py \
  --name redactor-dashboard-measurement \
  --receipt benchmarks/results/dashboard-overhead-container.json \
  -- tools/benchmarks/dashboard.py \
  --output benchmarks/results/dashboard-overhead.json
```

## Reproduction

Weights and large generated inputs are not committed. Download them during setup, then run local inference without network access. Keep the private remote ledger to replay responses and retain budget accounting.

```sh
uv sync --locked
uv run --no-sync python tools/benchmarks/fetch_models.py
uv run --no-sync python tools/make_ocr_corpus.py
docker build -t redactor:local .
docker build -t redactor:evaluation -f tools/benchmarks/Dockerfile tools/benchmarks
uv run --no-sync python tools/benchmarks/run_container.py \
  --name redactor-eval-edge --receipt benchmarks/results/gliner-edge-container.json \
  -- tools/evaluate_text.py --backend gliner --model .models/gliner-pii-edge-v1.0 \
  --output benchmarks/results/gliner-edge.json
uv run --no-sync --env-file .env python tools/evaluate_remote.py \
  --model deepseek/deepseek-v4.1-flash-1017 --output benchmarks/results/deepseek-flash.json
uv run --no-sync --env-file .env python tools/evaluate_remote_ocr.py \
  --model deepseek/deepseek-v4.1-flash-1017 --output benchmarks/results/deepseek-flash-vision.json
```

The actual container runs used the existing production dependency image because a fresh build timed out downloading the spaCy wheel. Current source was mounted into the evaluation container. Each container receipt records the exact image ID, source hash, command, limits and OOM status. The measurements therefore do not validate a fresh production image build.

Configuration selects GLiNER PII Edge UINT8, PP-OCRv5 mobile English and `z-ai/glm-5.3-flash`. These selections are based on this comparison, not complete end-to-end validation. Production NER supports spaCy and the pinned token-level GLiNER exports with the same adapter as evaluation; hosted detection is integrated into analysis with local fallback. PP-OCR and saved-image verification are not integrated into publication. No remote judge is selected because judging was not benchmarked.

The corpus is small, synthetic and partly assignment-derived. Published model-card scores were not mixed with these measurements. Detection, identity resolution, document rewriting, image masking, the optional remote judge, SIGKILL recovery and the large-CSV acceptance test remain distinct validation tasks.

GLiNER parity can be reproduced in a separate environment with `gliner==0.2.30`, `torch==2.15.0`, `transformers==5.22.1`, `onnxruntime==1.31.1`, `tokenizers==0.23.3` and Pydantic installed. Run `PYTHONPATH=src HF_HUB_OFFLINE=1 python tools/benchmarks/compare_gliner.py --output benchmarks/results/gliner-parity.json` from the repository root. PyTorch is used only for this reference comparison.
