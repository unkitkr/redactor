"""Compare hosted text models with either live requests or explicit offline replay."""

import argparse
import hashlib
import json
import os
import subprocess
from collections import Counter
from pathlib import Path
from time import perf_counter

from redactor.evaluation.remote import (
    load_remote_ner,
    remote_settings,
    with_local_fallback,
)
from redactor.evaluation.replay import load_replay_ner, replay_state
from redactor.evaluation.state import evaluation_state
from redactor.evaluation.text import evaluate_text_examples
from redactor.inference.model_loader import load_local_ner
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
    PIPELINE_VERSION,
    STEP_ANALYZE,
    VERIFIER_VERSION,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", choices=EVALUATION_REMOTE_MODELS, required=True)
    parser.add_argument("--state", type=Path, default=Path(EVALUATION_REMOTE_STATE))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--previous-result", type=Path)
    parser.add_argument(
        "--replay-processing-version",
        help=(
            "Read historical decisions only; requires --previous-result "
            "and makes no API calls."
        ),
    )
    arguments = parser.parse_args()
    if arguments.replay_processing_version is not None and (
        not arguments.replay_processing_version or not arguments.previous_result
    ):
        parser.error(
            "--replay-processing-version requires --previous-result and a version"
        )
    corpus_path = Path(EVALUATION_TEXT_CORPUS)
    corpus = corpus_path.read_bytes()
    corpus_sha256 = hashlib.sha256(corpus).hexdigest()
    examples = tuple(TextExample.model_validate(item) for item in json.loads(corpus))
    previous = None
    previous_sha256 = None
    if arguments.previous_result:
        previous_bytes = arguments.previous_result.read_bytes()
        previous_sha256 = hashlib.sha256(previous_bytes).hexdigest()
        previous = json.loads(previous_bytes)
        if (
            previous["model"] != arguments.model
            or previous["corpus_sha256"] != corpus_sha256
        ):
            parser.error(
                "Previous result must have the same model and corpus fingerprint"
            )
    offline = arguments.replay_processing_version is not None
    state_context = replay_state if offline else evaluation_state
    cache_counts: Counter[str] = Counter()

    def record_cache_event(event: str) -> None:
        cache_counts[event] += 1

    with state_context(arguments.state, corpus_path, STEP_ANALYZE) as (
        connection,
        claimed,
        mapping_key,
    ):
        if offline:
            remote = load_replay_ner(
                connection,
                claimed,
                arguments.model,
                mapping_key,
                arguments.replay_processing_version,
                record_cache_event,
            )
        else:
            remote = load_remote_ner(
                connection,
                claimed,
                arguments.model,
                mapping_key,
                os.environ[EVALUATION_OPENROUTER_KEY],
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
            "source_revision": subprocess.check_output(
                ["git", "rev-parse", "HEAD"], text=True
            ).strip(),
            "source_worktree_dirty": bool(
                subprocess.check_output(
                    ["git", "status", "--porcelain"], text=True
                ).strip()
            ),
            "pipeline_version": PIPELINE_VERSION,
            "verifier_version": VERIFIER_VERSION,
            "request_settings": remote_settings(arguments.model).remote.model_dump(
                mode="json"
            ),
            "corpus_sha256": corpus_sha256,
            "remote_models_enabled": not offline,
            "offline_replay": offline,
            "cache_processing_version": arguments.replay_processing_version,
            "previous_result_sha256": previous_sha256,
            "verifier_model": "en_core_web_sm 3.8.0 (mandatory local checks)",
            "replay_rescoring": bool(arguments.previous_result),
            "evaluations": [
                (
                    previous["evaluations"][0]
                    if previous is not None
                    else evaluate_text_examples(examples, remote, combined=False)
                ),
                evaluate_text_examples(
                    examples, fallback, combined=True, verifier_adapter=local
                ),
            ],
            "fallbacks": dict(failures),
            "cache_counts": dict(cache_counts),
            "seconds": perf_counter() - started,
            "shared_conservative_accounted_usd": accounted_cost(
                connection, EVALUATION_REMOTE_VERSION
            )
            / 1_000_000_000,
        }
        if offline:
            report["new_model_requests"] = 0
            report["new_model_cost_usd"] = 0
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
