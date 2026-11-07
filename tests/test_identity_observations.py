"""Exercise encrypted evidence, atomic CSV progress and real worker death."""

import signal
import sqlite3
import subprocess
import sys
from datetime import date
from pathlib import Path

import pytest

from redactor.formats.csv import inspect_csv, iter_csv_records
from redactor.identity.evidence import observation_preparer, prepare_observation
from redactor.persistence.database import state_directory
from redactor.persistence.files.registration import register_file
from redactor.persistence.identities.observations import (
    iter_observations,
    save_observation_batch,
    scan_progress,
)
from redactor.persistence.queue.tasks import (
    claim_task,
    complete_task,
    get_task,
    recover_interrupted,
)
from redactor.schemas.identity import IdentityEvidence
from redactor.utils.constants import DEFAULT_RECORD_BYTES
from redactor.utils.errors import ERROR_STALE_ATTEMPT, ERROR_STEP_RESULT


def test_evidence_and_csv_cursor_recover_together_after_sigkill(
    connection: sqlite3.Connection, tmp_path: Path
) -> None:
    source = tmp_path / "records.csv"
    source.write_text(
        "patient,mrn,birth_date,event_date\n"
        "John Smith,00123,1936-01-02,2025-03-04\n"
        '"Smith, John",00123,1936-01-02,2026-04-05\n',
        encoding="utf-8",
    )
    registered = register_file(connection, source, "analyze", "identity-scan-v1")
    process = subprocess.run(
        [
            sys.executable,
            str(Path(__file__).parent / "support" / "crash_after_identity_batch.py"),
            str(state_directory(connection)),
        ],
        check=False,
        timeout=5,
    )
    assert process.returncode == -signal.SIGKILL
    stale = get_task(connection, registered.task_id)
    recover_interrupted(connection)
    resumed = claim_task(connection)
    assert resumed is not None
    progress = scan_progress(connection, resumed.task_id)
    assert progress is not None and progress.record_count == 1
    layout = inspect_csv(source, DEFAULT_RECORD_BYTES)
    remaining = list(
        iter_csv_records(
            source,
            layout,
            DEFAULT_RECORD_BYTES,
            start_offset=progress.input_offset,
            completed_records=progress.record_count,
        )
    )
    assert len(remaining) == 1 and remaining[0].number == 2
    name, identifier, birth, reference = remaining[0].values
    batch = (
        IdentityEvidence(
            role="patient",
            name=name,
            identifier=identifier,
            identifier_namespace="mrn",
            birth_date=date.fromisoformat(birth),
            reference_date=date.fromisoformat(reference),
            explicit_older_age=True,
            context_key="record-2",
        ),
    )
    key = bytes(range(32))
    with pytest.raises(ValueError, match=ERROR_STALE_ATTEMPT):
        save_observation_batch(
            connection,
            stale,
            batch,
            key,
            sequence=2,
            input_offset=source.stat().st_size,
            record_count=2,
        )
    before = connection.execute(
        "SELECT encrypted_payload FROM identity_observations"
    ).fetchone()[0]
    connection.execute(
        "CREATE TEMP TRIGGER fail_progress BEFORE UPDATE ON identity_scan_progress "
        "BEGIN SELECT RAISE(ABORT, 'test progress failure'); END"
    )
    with pytest.raises(sqlite3.IntegrityError):
        save_observation_batch(
            connection,
            resumed,
            batch,
            key,
            sequence=2,
            input_offset=source.stat().st_size,
            record_count=2,
        )
    assert scan_progress(connection, resumed.task_id) == progress
    assert (
        connection.execute(
            "SELECT encrypted_payload FROM identity_observations"
        ).fetchone()[0]
        == before
    )
    connection.execute("DROP TRIGGER fail_progress")
    committed = save_observation_batch(
        connection,
        resumed,
        batch,
        key,
        sequence=2,
        input_offset=source.stat().st_size,
        record_count=2,
    )
    assert (
        save_observation_batch(
            connection,
            resumed,
            batch,
            key,
            sequence=2,
            input_offset=source.stat().st_size,
            record_count=2,
        )
        == committed
    )
    with pytest.raises(ValueError, match=ERROR_STEP_RESULT):
        list(iter_observations(connection, resumed.task_id, key))
    complete_task(connection, resumed)
    saved = list(iter_observations(connection, resumed.task_id, key))
    assert len(saved) == 1
    assert saved[0].evidence.reference_date == date(2026, 4, 5)
    assert saved[0].evidence.explicit_older_age
    assert "John Smith" not in "\n".join(connection.iterdump())


def test_repeated_evidence_advances_cursor_without_reencrypting_unchanged_people(
    connection: sqlite3.Connection, tmp_path: Path
) -> None:
    source = tmp_path / "repeated.csv"
    source.write_text("record\nfirst\nsecond\nthird\n", encoding="utf-8")
    register_file(connection, source, "analyze", "identity-noop-v1")
    task = claim_task(connection)
    assert task is not None
    key = bytes(range(32))
    prepare = observation_preparer(key)
    patient = IdentityEvidence(
        role="patient",
        name="Alice Stone",
        identifier="12345",
        identifier_namespace="mrn",
        birth_date=date(1936, 1, 2),
        reference_date=date(2025, 1, 2),
        context_key="first-patient",
    )
    provider = patient.model_copy(
        update={"role": "provider", "birth_date": None, "context_key": "first-provider"}
    )
    save_observation_batch(
        connection,
        task,
        (patient, provider),
        key,
        sequence=1,
        input_offset=len("record\nfirst\n"),
        record_count=1,
        counts={"name": 2},
        observation_reader=prepare,
    )
    saved = connection.execute(
        "SELECT * FROM identity_observations ORDER BY observation_key"
    ).fetchall()
    repeated = tuple(
        person.model_copy(update={"context_key": f"second-{person.role}"})
        for person in (patient, provider)
    )
    connection.execute(
        "CREATE TEMP TRIGGER reject_unchanged_observation "
        "BEFORE UPDATE ON identity_observations "
        "BEGIN SELECT RAISE(ABORT, 'unchanged evidence rewritten'); END"
    )
    changes = connection.total_changes
    progress = save_observation_batch(
        connection,
        task,
        repeated,
        key,
        sequence=2,
        input_offset=len("record\nfirst\nsecond\n"),
        record_count=2,
        counts={"name": 4},
        observation_reader=prepare,
    )
    assert connection.total_changes == changes + 1
    assert progress.record_count == 2 and progress.counts == {"name": 4}
    assert (
        connection.execute(
            "SELECT * FROM identity_observations ORDER BY observation_key"
        ).fetchall()
        == saved
    )
    changes = connection.total_changes
    assert (
        save_observation_batch(
            connection,
            task,
            repeated,
            key,
            sequence=2,
            input_offset=len("record\nfirst\nsecond\n"),
            record_count=2,
            counts={"name": 4},
            observation_reader=prepare,
        )
        == progress
    )
    assert connection.total_changes == changes
    connection.execute("DROP TRIGGER reject_unchanged_observation")

    older = patient.model_copy(
        update={
            "context_key": "third-patient",
            "reference_date": date(2026, 1, 2),
            "explicit_older_age": True,
        }
    )
    conflicting = patient.model_copy(update={"birth_date": date(1986, 1, 2)})
    incomplete = patient.model_copy(
        update={"birth_date": None, "context_key": "third-a"}
    )
    save_observation_batch(
        connection,
        task,
        (
            older,
            provider,
            conflicting,
            incomplete,
            incomplete.model_copy(update={"context_key": "third-b"}),
        ),
        key,
        sequence=3,
        input_offset=task.input_size,
        record_count=3,
        counts={"name": 9},
        observation_reader=prepare,
    )
    complete_task(connection, task)
    observations = tuple(iter_observations(connection, task.task_id, key))
    assert len(observations) == 5
    for item in observations:
        assert prepare(item.evidence) == prepare_observation(item.evidence, key)
    for evidence in (
        older,
        provider,
        conflicting,
        incomplete,
        incomplete.model_copy(update={"context_key": "third-b"}),
        older.model_copy(update={"issuer": "another issuer"}),
    ):
        assert prepare(evidence) == prepare_observation(evidence, key)
    matched = next(
        item for item in observations if item.evidence.birth_date == patient.birth_date
    )
    assert matched.evidence.reference_date == date(2026, 1, 2)
    assert matched.evidence.explicit_older_age
    assert (
        len({item.observation_key for item in observations if not item.is_anchor}) == 2
    )
    assert connection.execute(
        "SELECT encrypted_payload FROM identity_observations WHERE observation_key = ?",
        (
            next(
                item.observation_key
                for item in observations
                if item.evidence.role == "provider"
            ),
        ),
    ).fetchone()[0] in {row["encrypted_payload"] for row in saved}
