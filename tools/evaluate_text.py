"""Evaluate an interchangeable local NER adapter without calling hosted models."""

import argparse
import hashlib
import importlib.metadata
import json
import os
import platform
import resource
import subprocess
import sys
from pathlib import Path
from time import perf_counter

from redactor.evaluation.text import evaluate_text_examples
from redactor.inference.ner import load_local_ner
from redactor.schemas.configuration import LocalSettings
from redactor.schemas.evaluation import TextExample
from redactor.utils.constants import (
    DEFAULT_SPACY_MODEL,
    EVALUATION_TEXT_CORPUS,
    VERIFIER_VERSION,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default=DEFAULT_SPACY_MODEL)
    parser.add_argument(
        "--backend", choices=("spacy", "gliner", "openmed"), default="spacy"
    )
    parser.add_argument("--corpus", type=Path, default=Path(EVALUATION_TEXT_CORPUS))
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()
    corpus = arguments.corpus.read_bytes()
    examples = tuple(TextExample.model_validate(item) for item in json.loads(corpus))
    if len({example.case_id for example in examples}) != len(examples):
        raise ValueError("Duplicate evaluation case identifiers")
    started = perf_counter()
    if arguments.backend == "gliner":
        from redactor.evaluation.gliner import load_gliner

        adapter = load_gliner(Path(arguments.model))
    elif arguments.backend == "openmed":
        from redactor.evaluation.openmed import load_openmed

        adapter = load_openmed(Path(arguments.model))
    else:
        adapter = load_local_ner(LocalSettings(spacy_model=arguments.model))
    load_seconds = perf_counter() - started
    report = {
        "scope": (
            "Manually annotated synthetic challenge set, not a population recall "
            "estimate or a full-document verification benchmark."
        ),
        "model": arguments.model,
        "model_version": (
            importlib.metadata.version(arguments.model.replace("_", "-"))
            if arguments.backend == "spacy"
            else "see model-artifacts.json"
        ),
        "spacy_version": importlib.metadata.version("spacy"),
        "python": platform.python_version(),
        "platform": platform.platform(),
        "revision": os.environ.get("REDACTOR_EVALUATION_REVISION")
        or subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
        "dirty_tree": (
            os.environ.get("REDACTOR_EVALUATION_DIRTY", "true") == "true"
            if "REDACTOR_EVALUATION_REVISION" in os.environ
            else bool(
                subprocess.check_output(
                    ["git", "status", "--porcelain"], text=True
                ).strip()
            )
        ),
        "corpus_sha256": hashlib.sha256(corpus).hexdigest(),
        "remote_models_enabled": False,
        "verifier_version": VERIFIER_VERSION,
        "model_load_seconds": load_seconds,
        "evaluations": [
            evaluate_text_examples(examples, adapter, combined=mode)
            for mode in (False, True)
        ],
    }
    report["peak_process_rss_bytes"] = resource.getrusage(
        resource.RUSAGE_SELF
    ).ru_maxrss * (1 if sys.platform == "darwin" else 1024)
    report["backend"] = arguments.backend
    cgroup_peak = Path("/sys/fs/cgroup/memory.peak")
    report["peak_cgroup_bytes"] = (
        int(cgroup_peak.read_text()) if cgroup_peak.exists() else None
    )
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_text(json.dumps(report, indent=2) + "\n")
    print(
        json.dumps(
            {
                "model": report["model"],
                "evaluations": [
                    {
                        "mode": item["mode"],
                        "counts": item["exact_typed_span_counts"],
                        "totals": item["totals"],
                    }
                    for item in report["evaluations"]
                ],
            }
        )
    )


if __name__ == "__main__":
    main()
