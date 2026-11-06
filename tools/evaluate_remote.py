"""Run paid text-model comparisons through the production durable provider."""

import argparse
import hashlib
import json
import os
from collections import Counter
from pathlib import Path
from time import perf_counter

from redactor.evaluation.remote import (
    load_remote_ner,
    remote_settings,
    with_local_fallback,
)
from redactor.evaluation.state import evaluation_state
from redactor.evaluation.text import evaluate_text_examples
from redactor.inference.ner import load_local_ner
from redactor.persistence.models.budget import accounted_cost
from redactor.schemas.configuration import LocalSettings
from redactor.schemas.evaluation import TextExample
from redactor.utils.constants import (
    EVALUATION_OPENROUTER_KEY,
    EVALUATION_REMOTE_MODELS,
    EVALUATION_REMOTE_RECEIPTS,
    EVALUATION_REMOTE_STATE,
    EVALUATION_REMOTE_VERSION,
    EVALUATION_TEXT_CORPUS,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", choices=EVALUATION_REMOTE_MODELS, required=True)
    parser.add_argument("--state", type=Path, default=Path(EVALUATION_REMOTE_STATE))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--previous-result", type=Path)
    arguments = parser.parse_args()
    api_key = os.environ[EVALUATION_OPENROUTER_KEY]
    corpus_path = Path(EVALUATION_TEXT_CORPUS)
    corpus = corpus_path.read_bytes()
    examples = tuple(TextExample.model_validate(item) for item in json.loads(corpus))
    with evaluation_state(arguments.state, corpus_path, "analyze") as (
        connection,
        claimed,
        mapping_key,
    ):
        remote = load_remote_ner(
            connection,
            claimed,
            arguments.model,
            mapping_key,
            api_key,
            arguments.state / EVALUATION_REMOTE_RECEIPTS,
        )
        local = load_local_ner(LocalSettings())
        failures: Counter[str] = Counter()

        def record_failure(reason: str) -> None:
            failures[reason] += 1

        fallback = with_local_fallback(remote, local, record_failure)
        started = perf_counter()
        report = {
            "scope": (
                "Synthetic text-unit detection and policy evaluation, "
                "not native-file publication or a remote judge evaluation."
            ),
            "model": arguments.model,
            "request_settings": remote_settings(arguments.model).remote.model_dump(
                mode="json"
            ),
            "corpus_sha256": hashlib.sha256(corpus).hexdigest(),
            "remote_models_enabled": True,
            "verifier_model": "en_core_web_sm 3.8.0 (mandatory local checks)",
            "replay_rescoring": bool(arguments.previous_result),
            "evaluations": [
                (
                    json.loads(arguments.previous_result.read_text())["evaluations"][0]
                    if arguments.previous_result
                    else evaluate_text_examples(examples, remote, combined=False)
                ),
                evaluate_text_examples(
                    examples, fallback, combined=True, verifier_adapter=local
                ),
            ],
            "fallbacks": dict(failures),
            "seconds": perf_counter() - started,
            "shared_conservative_accounted_usd": accounted_cost(
                connection, EVALUATION_REMOTE_VERSION
            )
            / 1_000_000_000,
        }
        arguments.output.parent.mkdir(parents=True, exist_ok=True)
        arguments.output.write_text(json.dumps(report, indent=2) + "\n")
        print(
            json.dumps(
                {
                    "model": arguments.model,
                    "seconds": report["seconds"],
                    "fallbacks": report["fallbacks"],
                    "accounted_usd": report["shared_conservative_accounted_usd"],
                }
            ),
            flush=True,
        )


if __name__ == "__main__":
    main()
