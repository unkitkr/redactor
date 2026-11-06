"""Measure an OCR adapter on labelled source pixels without publishing documents."""

import argparse
import hashlib
import importlib.metadata
import json
import platform
import resource
import subprocess
import sys
from pathlib import Path
from time import perf_counter

from redactor.evaluation.ocr import evaluate_ocr
from redactor.evaluation.ocr_adapters import load_ppocr, load_tesseract
from redactor.schemas.evaluation import OcrExample
from redactor.utils.constants import EVALUATION_OCR_CORPUS


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backend", choices=("tesseract", "ppocr"), required=True)
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--language", choices=("en", "latin"), default="en")
    parser.add_argument("--corpus", type=Path, default=Path(EVALUATION_OCR_CORPUS))
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()
    corpus = arguments.corpus.read_bytes()
    examples = tuple(OcrExample.model_validate(item) for item in json.loads(corpus))
    started = perf_counter()
    if arguments.backend == "tesseract":
        adapter = load_tesseract(arguments.model)
        runtime = subprocess.check_output(
            ["tesseract", "--version"], text=True
        ).splitlines()[0]
    else:
        adapter = load_ppocr(arguments.model, arguments.language)
        runtime = "rapidocr " + importlib.metadata.version("rapidocr")
    loaded = perf_counter()
    result = evaluate_ocr(examples, adapter)
    finished = perf_counter()
    peak = Path("/sys/fs/cgroup/memory.peak")
    report = {
        "scope": (
            "OCR text and bounding-box evaluation, "
            "not PHI classification or safe image publication."
        ),
        "backend": arguments.backend,
        "model": str(arguments.model),
        "language": arguments.language,
        "runtime": runtime,
        "python": platform.python_version(),
        "platform": platform.platform(),
        "corpus_sha256": hashlib.sha256(corpus).hexdigest(),
        "model_load_seconds": loaded - started,
        "inference_seconds": finished - loaded,
        "peak_process_rss_bytes": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        * (1 if sys.platform == "darwin" else 1024),
        "peak_cgroup_bytes": int(peak.read_text()) if peak.exists() else None,
        "evaluation": result,
    }
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_text(json.dumps(report, indent=2) + "\n")
    print(
        json.dumps(
            {
                "backend": arguments.backend,
                "model": str(arguments.model),
                "totals": result["totals"],
            }
        )
    )


if __name__ == "__main__":
    main()
