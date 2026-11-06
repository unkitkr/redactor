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

Raw NER can over-detect values that the policy later preserves. The clinical column measures overlap with explicitly labelled clinical spans; it is not a count of published changes. The current policy produced zero such clinical-span edits on this corpus, but still missed identifiers in some accepted cases.

The local exports use pinned tokenizers and checksummed weights from [model-artifacts.json](model-artifacts.json). GLiNER uses a fixed 0.3 threshold and explicit identifier labels, with token-level start/end/inside decoding and no truncation. OpenMed uses its BIO labels, joins adjacent first/last-name components, and trims tokenizer whitespace. The GLiNER decoder matched the upstream `gliner` 0.2.30 wrapper on all 71 Edge and 69 Small inputs, including masked and rewritten text ([parity results](results/gliner-parity.json)). A tied-score ordering discrepancy was corrected before the final measurements. OpenMed uses custom BIO grouping without a separate upstream parity comparison.

NVIDIA `nvidia/gliner-PII` is [excluded by resource preflight](results/nvidia-preflight.json): its published weight file is 1,782,000,995 bytes. No inference or OOM experiment was run, so no accuracy is claimed. OpenMed completed but reached 1 GiB cgroup memory and about 1003 MiB process RSS during loading; that leaves insufficient demonstrated headroom for the full pipeline.

## Combined policy and verifier

| Detector | Policy abstentions / 40 | Verifier checked | False accepts | False rejects |
| --- | ---: | ---: | ---: | ---: |
| spaCy en_core_web_sm 3.8.0 | 11 | 29 | 2 | 1 |
| GLiNER PII Edge v1.0 UINT8 | 22 | 18 | 0 | 1 |
| GLiNER PII Small v1.0 UINT8 | 20 | 20 | 2 | 1 |
| OpenMed SuperClinical Small INT8 | 14 | 26 | 0 | 1 |
| deepseek/deepseek-v4.1-flash-1017 | 9 | 31 | 2 | 3 |
| deepseek/deepseek-v4-pro | 11 | 29 | 1 | 2 |
| z-ai/glm-5.3-flash | 8 | 32 | 1 | 3 |

A false accept means the text-unit verifier accepted a result with an incompletely covered reference identifier or a changed clinical reference span. These are not full-file publication measurements. Zero false accepts with many abstentions does not establish high recall. Observed escapes include partially handled initialled names, international telephone numbers, and candidate-specific missed names or facilities. The current verifier must be strengthened before these results can support publication safety.

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

## Reproduction

Weights and large generated inputs are not committed. Download them during setup, then run local inference without network access. Keep the private remote ledger to replay responses and retain budget accounting.

```sh
uv sync --frozen
uv pip install -r tools/benchmarks/requirements.txt
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

Configuration now selects GLiNER PII Edge UINT8, PP-OCRv5 mobile English and `z-ai/glm-5.3-flash`. These selections are based on this comparison, not an end-to-end validation. The production NER loader still supports only spaCy, so selecting GLiNER currently fails closed when inference is needed; PP-OCR and hosted detection are not integrated into the publication path. No remote judge is selected because judging was not benchmarked.

The corpus is small, synthetic and partly assignment-derived. Published model-card scores were not mixed with these measurements. Detection, identity resolution, document rewriting, image masking, the optional remote judge, SIGKILL recovery and the large-CSV acceptance test remain distinct validation tasks.

GLiNER parity can be reproduced in a separate environment with `gliner==0.2.30`, `torch==2.15.0`, `transformers==5.22.1`, `onnxruntime==1.31.1`, `tokenizers==0.23.3` and Pydantic installed. Run `PYTHONPATH=src HF_HUB_OFFLINE=1 python tools/benchmarks/compare_gliner.py --output benchmarks/results/gliner-parity.json` from the repository root. PyTorch is used only for this reference comparison.
