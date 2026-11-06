"""Real SQLite integration for crash accounting and encrypted fallback replay."""

import signal
import sqlite3
import subprocess
import sys
from pathlib import Path

from redactor.persistence.database import state_directory
from redactor.persistence.files import register_file
from redactor.persistence.model_budget import (
    accounted_cost,
    recover_model_attempts,
    reserve_attempt,
    settle_attempt,
)
from redactor.persistence.model_decisions import (
    read_model_decision,
    save_model_decision,
)
from redactor.persistence.queue import claim_task, recover_interrupted
from redactor.schemas.configuration import RemoteSettings
from redactor.schemas.provider import (
    ModelDecision,
    ModelReservation,
    ModelUnavailable,
    ModelUsage,
)
from redactor.utils.errors import (
    ERROR_MODEL_AUTH,
    ERROR_MODEL_BUDGET,
    ERROR_MODEL_CIRCUIT,
    ERROR_MODEL_TRANSIENT,
)


def test_sigkill_keeps_unconfirmed_cost_reserved_after_recovery(
    connection: sqlite3.Connection, source_file: Path
) -> None:
    register_file(connection, source_file, "analyze", "model-accounting-v1")
    process = subprocess.run(
        [
            sys.executable,
            str(Path(__file__).parent / "support" / "crash_after_reservation.py"),
            str(state_directory(connection)),
        ],
        check=False,
        timeout=5,
    )
    assert process.returncode == -signal.SIGKILL
    recover_interrupted(connection)
    recover_model_attempts(connection)
    claimed = claim_task(connection)
    assert claimed is not None
    assert accounted_cost(connection, claimed.processing_version) == 700
    denied = reserve_attempt(
        connection, claimed, "request-a", 700, 1000, RemoteSettings()
    )
    assert denied == ModelUnavailable(reason_code=ERROR_MODEL_BUDGET)
    affordable = reserve_attempt(
        connection, claimed, "request-b", 300, 1000, RemoteSettings()
    )
    assert isinstance(affordable, ModelReservation)
    settle_attempt(
        connection,
        claimed,
        affordable,
        ModelUsage(input_tokens=10, output_tokens=5, cost_nanos=120),
    )
    assert accounted_cost(connection, claimed.processing_version) == 820


def test_model_decisions_replay_encrypted_and_circuit_state_is_shared(
    connection: sqlite3.Connection, source_file: Path
) -> None:
    register_file(connection, source_file, "analyze", "model-accounting-v1")
    claimed = claim_task(connection)
    assert claimed is not None
    key = bytes(range(32))
    settings = RemoteSettings(circuit_failures=1)
    response = ModelDecision(
        backend="remote", payload={"private": "Synthetic evidence"}
    )
    assert (
        save_model_decision(connection, claimed, "answer", response, key, settings)
        == response
    )
    assert read_model_decision(connection, "answer", key) == response
    raw = connection.execute(
        "SELECT encrypted_payload FROM model_decisions WHERE request_key = 'answer'"
    ).fetchone()[0]
    assert b"Synthetic evidence" not in raw
    fallback = ModelDecision(backend="local", reason_code=ERROR_MODEL_TRANSIENT)
    assert (
        save_model_decision(connection, claimed, "answer", fallback, key, settings)
        == response
    )
    save_model_decision(
        connection, claimed, "failed", fallback, key, settings, transient_failure=True
    )
    assert reserve_attempt(connection, claimed, "next", 10, 1000, settings) == (
        ModelUnavailable(reason_code=ERROR_MODEL_CIRCUIT)
    )
    revoked = ModelDecision(backend="local", reason_code=ERROR_MODEL_AUTH)
    save_model_decision(
        connection, claimed, "revoked", revoked, key, settings, disable_remote=True
    )
    assert reserve_attempt(connection, claimed, "later", 10, 1000, settings) == (
        ModelUnavailable(reason_code=ERROR_MODEL_AUTH)
    )
