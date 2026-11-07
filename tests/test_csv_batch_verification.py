"""Compare real serial and batched verification of saved multiline Unicode CSV."""

import csv
import sqlite3
from pathlib import Path

import pytest

from redactor.coordinator.bootstrap import prepare_run
from redactor.inference.model_loader import load_local_ner_adapters
from redactor.persistence.files.artifacts import inspect_artifact
from redactor.persistence.files.results import accepted_artifact, read_step_result
from redactor.persistence.queue.tasks import claim_task
from redactor.schemas.configuration import PipelineSettings
from redactor.schemas.entities import TextEntity
from redactor.schemas.verification import VerificationVerdict
from redactor.utils.constants import VERIFICATION_BATCH_RECORDS
from redactor.verification.csv import verify_csv
from redactor.workers.handlers import pipeline_handlers
from redactor.workers.pipeline import execute_task


@pytest.mark.parametrize("unresolved_prose", (False, True))
def test_csv_batch_matches_serial_verdict_and_rejects_saved_damage(
    connection: sqlite3.Connection, tmp_path: Path, unresolved_prose: bool
) -> None:
    source = tmp_path / "input"
    source.mkdir()
    path = source / "records.csv"
    note = "Glucose 106 mg/dL.\nTemperature 37 °C.\nCall 206-555-0101."
    if unresolved_prose:
        note += "\nFollow-up discussed."
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream, quoting=csv.QUOTE_ALL)
        writer.writerow(("patient", "mrn", "birth_date", "admit_ts", "comments"))
        for index in range(VERIFICATION_BATCH_RECORDS + 3):
            name = "Renée Marin" if index % 2 else "Rene\u0301e Marin"
            writer.writerow(
                (
                    name,
                    "27193",
                    "1974-02-08",
                    "2026-04-05",
                    note,
                )
            )
    original = path.read_bytes()
    settings = PipelineSettings()
    key = bytes(range(32))
    single, batch = load_local_ner_adapters(settings.local)
    assert batch is not None
    batches = 0

    def counted_batch(texts: tuple[str, ...]) -> tuple[tuple[TextEntity, ...], ...]:
        nonlocal batches
        batches += 1
        assert batch is not None
        return batch(texts)

    run = prepare_run(connection, source, settings, key)
    handlers = pipeline_handlers(
        settings,
        key,
        single,
        run.resolution_task_id,
        verifier_ner=single,
        verification_batch=counted_batch,
    )
    for step in ("inspect", "analyze", "resolve", "rewrite"):
        task = claim_task(connection, step=step)
        assert task is not None, step
        execute_task(connection, task, handlers)
    assert task is not None
    artifact = accepted_artifact(connection, task.task_id)
    saved = artifact.path.read_bytes()
    verification = claim_task(connection, step="verify")
    assert verification is not None
    checks = []
    for adapter in (None, counted_batch):
        checks.append(
            verify_csv(
                connection,
                verification,
                artifact,
                settings=settings,
                mapping_key=key,
                local_ner=single,
                resolution_task_id=run.resolution_task_id,
                verification_batch=adapter,
            )
        )
    assert checks[0] == checks[1]
    assert all(check.status == "pass" for check in checks[0])
    # Exact source observations persist across batches; saved pseudonyms need no NER.
    assert batches == int(unresolved_prose)
    assert artifact.path.read_bytes() == saved
    assert b"106 mg/dL" in saved and b"206-555-0101" not in saved
    for corrupted in (
        saved.replace(b"106 mg/dL", b"107 mg/dL", 1),
        saved.replace(b"106 mg/dL.", b"106 mg/dL. Alice Stone.", 1),
        saved[: saved.index(b"\n") + 1],
    ):
        artifact.path.write_bytes(corrupted)
        changed = inspect_artifact(artifact.path, persist=False)
        for adapter in (None, counted_batch):
            with pytest.raises(ValueError):
                verify_csv(
                    connection,
                    verification,
                    changed,
                    settings=settings,
                    mapping_key=key,
                    local_ner=single,
                    resolution_task_id=run.resolution_task_id,
                    verification_batch=adapter,
                )
    artifact.path.write_bytes(saved)
    execute_task(connection, verification, handlers)
    verdict = read_step_result(connection, verification.task_id, VerificationVerdict)
    assert verdict.status == "pass" and verdict.checks == checks[0]
    publication = claim_task(connection, step="publish")
    assert publication is not None
    execute_task(connection, publication, handlers)
    assert (tmp_path / "output" / "published" / "records.csv").read_bytes() == saved
    assert path.read_bytes() == original


@pytest.mark.parametrize("mention", ("Alice Stone", "A. Stone"))
def test_csv_observation_cache_does_not_reuse_contextual_verdicts(
    connection: sqlite3.Connection, tmp_path: Path, mention: str
) -> None:
    source = tmp_path / "input"
    source.mkdir()
    path = source / "records.csv"
    canonical_text = f"Reviewed with {mention}; phone 000-000-0000; metformin 500 mg."
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(("patient", "mrn", "birth_date", "admit_ts", "comments"))
        for index in range(VERIFICATION_BATCH_RECORDS + 1):
            # The first batch has corroborated names. The last identical text has
            # no corresponding typed identity and must still get its own verdict.
            patient = (
                "Alice Stone" if index < VERIFICATION_BATCH_RECORDS else "Isabel Nash"
            )
            text = (
                f"Reviewed with {mention}; phone 206-555-{1000 + index}; "
                "metformin 500 mg."
            )
            writer.writerow((patient, str(index), "1975-02-08", "2026-04-05", text))
    settings = PipelineSettings()
    key = bytes(range(32))
    verifier, batch = load_local_ner_adapters(settings.local)
    assert batch is not None
    observed: list[str] = []

    def missed_detector(value: str) -> tuple[TextEntity, ...]:
        return ()

    def counted_batch(texts: tuple[str, ...]) -> tuple[tuple[TextEntity, ...], ...]:
        observed.extend(texts)
        assert batch is not None
        return batch(texts)

    run = prepare_run(connection, source, settings, key)
    handlers = pipeline_handlers(
        settings,
        key,
        missed_detector,
        run.resolution_task_id,
        verifier_ner=verifier,
        verification_batch=counted_batch,
    )
    for step in ("inspect", "analyze", "resolve", "rewrite"):
        task = claim_task(connection, step=step)
        assert task is not None, step
        execute_task(connection, task, handlers)
    verification = claim_task(connection, step="verify")
    assert verification is not None
    execute_task(connection, verification, handlers)
    verdict = read_step_result(connection, verification.task_id, VerificationVerdict)
    assert verdict.status == "fail"
    assert observed.count(canonical_text) == 1
    assert len(observed) == 1
    assert "metformin 500 mg" in observed[0]
    assert not (tmp_path / "output" / "published" / "records.csv").exists()


def test_csv_malformed_raw_date_never_reaches_statistical_normalization(
    connection: sqlite3.Connection, tmp_path: Path
) -> None:
    source = tmp_path / "input"
    source.mkdir()
    with (source / "records.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(("patient", "mrn", "birth_date", "admit_ts", "comments"))
        writer.writerow(
            (
                "Alice Stone",
                "27193",
                "1975-02-08",
                "2026-04-05",
                "Follow-up scheduled on 2026-13-05.",
            )
        )
    settings = PipelineSettings()
    key = bytes(range(32))
    seen: list[str] = []

    def no_entities(text: str) -> tuple[TextEntity, ...]:
        seen.append(text)
        return ()

    run = prepare_run(connection, source, settings, key)
    handlers = pipeline_handlers(settings, key, no_entities, run.resolution_task_id)
    while task := claim_task(connection):
        execute_task(connection, task, handlers)
    assert not (tmp_path / "output" / "published" / "records.csv").exists()
    assert (tmp_path / "output" / "quarantine" / "records.csv.reason.json").exists()
    assert seen == ["comments"]
