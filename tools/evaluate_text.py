"""Evaluate an interchangeable local NER adapter without calling hosted models."""

import argparse
import hashlib
import importlib.metadata
import json
import platform
import subprocess
from pathlib import Path
from time import perf_counter

from redactor.evaluation.text import evaluate_text_examples
from redactor.inference.ner import load_local_ner
from redactor.schemas.configuration import LocalSettings
from redactor.schemas.evaluation import TextExample
from redactor.utils.constants import DEFAULT_SPACY_MODEL, EVALUATION_TEXT_CORPUS


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default=DEFAULT_SPACY_MODEL)
    parser.add_argument("--corpus", type=Path, default=Path(EVALUATION_TEXT_CORPUS))
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()
    corpus = arguments.corpus.read_bytes()
    examples = tuple(TextExample.model_validate(item) for item in json.loads(corpus))
    if len({example.case_id for example in examples}) != len(examples):
        raise ValueError("Duplicate evaluation case identifiers")
    started = perf_counter()
    adapter = load_local_ner(LocalSettings(spacy_model=arguments.model))
    load_seconds = perf_counter() - started
    report = {
        "scope": (
            "Manually annotated synthetic challenge set, not a population recall "
            "estimate or a full-document verification benchmark."
        ),
        "model": arguments.model,
        "model_version": importlib.metadata.version(arguments.model.replace("_", "-")),
        "spacy_version": importlib.metadata.version("spacy"),
        "python": platform.python_version(),
        "platform": platform.platform(),
        "revision": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], text=True
        ).strip(),
        "dirty_tree": bool(
            subprocess.check_output(["git", "status", "--porcelain"], text=True).strip()
        ),
        "corpus_sha256": hashlib.sha256(corpus).hexdigest(),
        "remote_models_enabled": False,
        "model_load_seconds": load_seconds,
        "evaluations": [
            evaluate_text_examples(examples, adapter, combined=mode)
            for mode in (False, True)
        ],
    }
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
