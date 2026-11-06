"""Run paid OCR comparisons against fixed images without local fallback."""

import argparse
import hashlib
import json
import os
from pathlib import Path
from time import perf_counter

from redactor.evaluation.ocr import evaluate_ocr
from redactor.evaluation.remote_ocr import load_remote_ocr
from redactor.evaluation.state import evaluation_state
from redactor.persistence.models.budget import accounted_cost
from redactor.schemas.evaluation import OcrExample
from redactor.utils.constants import (
    EVALUATION_OCR_CORPUS,
    EVALUATION_OPENROUTER_KEY,
    EVALUATION_REMOTE_RECEIPTS,
    EVALUATION_REMOTE_STATE,
    EVALUATION_REMOTE_VERSION,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", required=True)
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()
    state = Path(EVALUATION_REMOTE_STATE)
    corpus_path = Path(EVALUATION_OCR_CORPUS)
    corpus = corpus_path.read_bytes()
    examples = tuple(OcrExample.model_validate(item) for item in json.loads(corpus))
    with evaluation_state(state, corpus_path, "evaluate_ocr") as (
        connection,
        claimed,
        mapping_key,
    ):
        adapter = load_remote_ocr(
            connection,
            claimed,
            arguments.model,
            mapping_key,
            os.environ[EVALUATION_OPENROUTER_KEY],
            state / EVALUATION_REMOTE_RECEIPTS,
        )
        started = perf_counter()
        report = {
            "scope": (
                "Hosted OCR transcription and localization, "
                "not image sanitization or a verifier verdict."
            ),
            "model": arguments.model,
            "remote_models_enabled": True,
            "corpus_sha256": hashlib.sha256(corpus).hexdigest(),
            "evaluation": evaluate_ocr(examples, adapter),
            "seconds": perf_counter() - started,
            "shared_conservative_accounted_usd": accounted_cost(
                connection, EVALUATION_REMOTE_VERSION
            )
            / 1_000_000_000,
        }
        arguments.output.write_text(json.dumps(report, indent=2) + "\n")
        print(
            json.dumps(
                {
                    "model": arguments.model,
                    "seconds": report["seconds"],
                    "accounted_usd": report["shared_conservative_accounted_usd"],
                }
            ),
            flush=True,
        )


if __name__ == "__main__":
    main()
