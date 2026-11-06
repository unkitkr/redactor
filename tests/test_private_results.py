"""Encrypted artifact persistence through completion and process-local reopen."""

import sqlite3
from contextlib import closing
from pathlib import Path

import pytest

from redactor.persistence.database import open_database, state_directory
from redactor.persistence.files import register_file
from redactor.persistence.queue import claim_task, complete_task
from redactor.persistence.results import read_step_result, write_step_result
from redactor.schemas.configuration import PipelineSettings, RemoteSettings
from redactor.utils.encryption import decrypt_payload, encrypt_payload
from redactor.utils.errors import ERROR_PRIVATE_RECORD


def test_private_result_survives_reopen_and_rejects_wrong_context_or_key(
    connection: sqlite3.Connection, source_file: Path
) -> None:
    register_file(connection, source_file, "analyze", "private-results-v1")
    claimed = claim_task(connection)
    assert claimed is not None
    # Any schema can exercise the private envelope without retaining PHI fixtures.
    private_text = "Synthetic confidential evidence"
    result = PipelineSettings(remote=RemoteSettings(model=private_text))
    key = bytes(range(32))
    artifact = write_step_result(connection, claimed, result, encryption_key=key)
    complete_task(connection, claimed, result=artifact)
    envelope = artifact.path.read_bytes()
    assert private_text.encode() not in envelope
    state = state_directory(connection)
    for database_file in state.glob("state.sqlite3*"):
        assert private_text.encode() not in database_file.read_bytes()

    with closing(open_database(state)) as reopened:
        assert (
            read_step_result(
                reopened, claimed.task_id, PipelineSettings, encryption_key=key
            )
            == result
        )
        with pytest.raises(ValueError, match=ERROR_PRIVATE_RECORD):
            read_step_result(
                reopened,
                claimed.task_id,
                PipelineSettings,
                encryption_key=bytes(reversed(key)),
            )

    with pytest.raises(ValueError, match=ERROR_PRIVATE_RECORD):
        decrypt_payload(key, envelope, context=b"a-different-evidence-record")
    altered = envelope[:-1] + bytes([envelope[-1] ^ 1])
    with pytest.raises(ValueError, match=ERROR_PRIVATE_RECORD):
        decrypt_payload(key, altered, context=claimed.task_id.encode())
    repeated = encrypt_payload(
        key, result.model_dump_json().encode(), context=claimed.task_id.encode()
    )
    assert repeated != envelope
    assert decrypt_payload(key, repeated, context=claimed.task_id.encode()) == (
        result.model_dump_json().encode()
    )
