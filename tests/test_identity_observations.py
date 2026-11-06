"""Exercise encrypted evidence, atomic CSV progress and real worker death."""

import signal
import sqlite3
import subprocess
import sys
from datetime import date
from pathlib import Path

import pytest

from redactor.formats.csv import inspect_csv, iter_csv_records
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
