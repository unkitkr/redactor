"""Call the steps directly. No workers, database, checkpoints or durable replay."""

import argparse
import json
import os
import time
from pathlib import Path
from tempfile import TemporaryDirectory

from redactor.inference.cache import cache_ner
from redactor.inference.runtime import runtime_adapters
from redactor.schemas.configuration import PipelineSettings
from redactor.schemas.entities import NerAdapter
from redactor.schemas.ocr import OcrAdapter
from redactor.schemas.simple import AnalyzedFile, SimpleFileResult
from redactor.utils.configuration import load_settings, read_mapping_key
from redactor.utils.constants import (
    CONFIGURATION_FILENAME,
    INPUT_DIRECTORY,
    OUTCOME_PUBLISHED,
    OUTCOME_QUARANTINED,
    PRIVATE_DIRECTORY_MODE,
    PUBLISHED_DIRECTORY,
    QUARANTINE_DIRECTORY,
    REASON_FILE_SUFFIX,
    REPORT_FILENAME,
    SIMPLE_MAX_FILES,
    SIMPLE_MAX_INPUT_BYTES,
    SIMPLE_MAX_RECORDS,
    SIMPLE_OUTPUT_DIRECTORY,
    SIMPLE_STAGE_EXTRACT,
    SIMPLE_STAGE_REDACT,
    SIMPLE_STAGE_RESOLVE,
    SIMPLE_STAGE_SAVE,
    STEP_ANALYZE,
    STEP_PUBLISH,
    STEP_VERIFY,
)
from redactor.utils.errors import ERROR_CONFIGURATION, ERROR_RESOURCE_LIMIT
from redactor.utils.failures import failure_reason
from simple_pipeline.content import extract_file, save_file
from simple_pipeline.identity import resolve_identities
from simple_pipeline.redact import analyze_file, redact_file
from simple_pipeline.verify import verify_saved


def run(
    input_directory: Path,
    output_directory: Path,
    settings: PipelineSettings,
    key: bytes,
    detector: NerAdapter,
    ocr: OcrAdapter,
    verifier: NerAdapter,
) -> tuple[SimpleFileResult, ...]:
    """Keep failures per file, and never place an unverified file in published/."""
    started = time.perf_counter()
    input_directory = input_directory.resolve(strict=True)
    output_directory = output_directory.resolve()
    if not input_directory.is_dir() or output_directory.is_relative_to(input_directory):
        raise ValueError(ERROR_CONFIGURATION)
    paths = sorted(path for path in input_directory.rglob("*") if path.is_file())
    if (
        len(paths) > SIMPLE_MAX_FILES
        or any(path.is_symlink() for path in paths)
        or sum(path.stat().st_size for path in paths) > SIMPLE_MAX_INPUT_BYTES
    ):
        raise ValueError(ERROR_RESOURCE_LIMIT)
    # A fresh directory prevents old results from looking like this run's output.
    output_directory.mkdir(parents=True, mode=PRIVATE_DIRECTORY_MODE)
    published = output_directory / PUBLISHED_DIRECTORY
    quarantine = output_directory / QUARANTINE_DIRECTORY
    published.mkdir(mode=PRIVATE_DIRECTORY_MODE)
    quarantine.mkdir(mode=PRIVATE_DIRECTORY_MODE)
    analyses: list[tuple[AnalyzedFile, SimpleFileResult]] = []
    results: list[SimpleFileResult] = []

    def record_failure(result: SimpleFileResult, error: Exception) -> None:
        failed = result.model_copy(
            update={
                "status": OUTCOME_QUARANTINED,
                "reason": failure_reason(error),
                "exception_type": type(error).__name__,
            }
        )
        reason_path = quarantine / (failed.input + REASON_FILE_SUFFIX)
        reason_path.parent.mkdir(parents=True, exist_ok=True)
        reason_path.write_text(failed.model_dump_json(indent=2) + "\n")
        results.append(failed)

    for path in paths:
        result = SimpleFileResult(
            input=path.relative_to(input_directory).as_posix(),
            status=OUTCOME_QUARANTINED,
            stage=SIMPLE_STAGE_EXTRACT,
        )
        tick = time.perf_counter()
        try:
            source = extract_file(path, settings)
            if (
                len(source.document.records)
                + sum(len(file.source.document.records) for file, _ in analyses)
                > SIMPLE_MAX_RECORDS
            ):
                raise ValueError(ERROR_RESOURCE_LIMIT)
            result.timings_seconds[SIMPLE_STAGE_EXTRACT] = time.perf_counter() - tick
            result = result.model_copy(
                update={
                    "input_sha256": source.sha256,
                    "file_type": source.inspection.file_type,
                    "records": len(source.document.records),
                    "stage": STEP_ANALYZE,
                }
            )
            tick = time.perf_counter()
            analysis = analyze_file(source, settings, detector, ocr)
            result.timings_seconds[STEP_ANALYZE] = time.perf_counter() - tick
            analyses.append((analysis, result))
        except Exception as error:
            result.timings_seconds[result.stage] = time.perf_counter() - tick
            record_failure(result, error)

    tick = time.perf_counter()
    try:
        lookup = resolve_identities(
            (analysis for analysis, _ in analyses),
            key,
            settings.policy.maximum_date_shift_days,
        )
    except Exception as error:
        for _, result in analyses:
            record_failure(
                result.model_copy(update={"stage": SIMPLE_STAGE_RESOLVE}), error
            )
        analyses.clear()
        lookup = resolve_identities((), key, settings.policy.maximum_date_shift_days)
    identity_seconds = time.perf_counter() - tick
    for analysis, result in analyses:
        # Temporary storage is only for saving and reopening the candidate.
        # It is not a checkpoint, ledger or recovery mechanism.
        with TemporaryDirectory(dir=output_directory) as temporary:
            candidate = Path(temporary) / analysis.source.path.name
            result = result.model_copy(update={"stage": SIMPLE_STAGE_REDACT})
            tick = time.perf_counter()
            try:
                plan = redact_file(analysis, lookup, key, settings)
                result.timings_seconds[SIMPLE_STAGE_REDACT] = time.perf_counter() - tick
                result = result.model_copy(update={"stage": SIMPLE_STAGE_SAVE})
                tick = time.perf_counter()
                save_file(plan, candidate, settings)
                result.timings_seconds[SIMPLE_STAGE_SAVE] = time.perf_counter() - tick
                result = result.model_copy(update={"stage": STEP_VERIFY})
                tick = time.perf_counter()
                digest = verify_saved(plan, candidate, settings, verifier, key)
                result.timings_seconds[STEP_VERIFY] = time.perf_counter() - tick
                result = result.model_copy(update={"stage": STEP_PUBLISH})
                destination = published / result.input
                destination.parent.mkdir(parents=True, exist_ok=True)
                candidate.rename(destination)
                results.append(
                    result.model_copy(
                        update={
                            "status": OUTCOME_PUBLISHED,
                            "output_sha256": digest,
                        }
                    )
                )
            except Exception as error:
                result.timings_seconds[result.stage] = time.perf_counter() - tick
                record_failure(result, error)

    ordered = tuple(sorted(results, key=lambda result: result.input))
    report = {
        "experiment": "direct-functions-local",
        "durability": False,
        "remote_calls": 0,
        "models": settings.local.model_dump(mode="json"),
        "elapsed_seconds": time.perf_counter() - started,
        "timings_seconds": {SIMPLE_STAGE_RESOLVE: identity_seconds},
        "published": sum(result.status == OUTCOME_PUBLISHED for result in ordered),
        "quarantined": sum(result.status == OUTCOME_QUARANTINED for result in ordered),
        "files": [result.model_dump(mode="json") for result in ordered],
    }
    (output_directory / REPORT_FILENAME).write_text(json.dumps(report, indent=2) + "\n")
    return ordered


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=Path(INPUT_DIRECTORY))
    parser.add_argument("--output", type=Path, default=Path(SIMPLE_OUTPUT_DIRECTORY))
    parser.add_argument("--config", type=Path, default=Path(CONFIGURATION_FILENAME))
    arguments = parser.parse_args()
    settings = load_settings(arguments.config)
    detector, ocr, verifier = runtime_adapters(settings.local, settings.resources)
    verifier = cache_ner(
        verifier,
        maximum_entries=settings.local.ner_cache_entries,
        maximum_text_characters=settings.local.ner_cache_characters,
    )
    # Mode is explicitly local, regardless of hosted settings in the shared TOML.
    os.umask(~PRIVATE_DIRECTORY_MODE & 0o777)
    results = run(
        arguments.input,
        arguments.output,
        settings,
        read_mapping_key(),
        detector,
        ocr,
        verifier,
    )
    print(
        json.dumps(
            {
                "published": sum(item.status == OUTCOME_PUBLISHED for item in results),
                "quarantined": sum(
                    item.status == OUTCOME_QUARANTINED for item in results
                ),
                "report": str(arguments.output / REPORT_FILENAME),
            }
        )
    )


if __name__ == "__main__":
    main()
