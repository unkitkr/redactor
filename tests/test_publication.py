"""Integration tests of the evidence gate, not clinical detection accuracy."""

import signal
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

from redactor.persistence.database import state_directory
from redactor.persistence.files import (
    create_temporary_file,
    register_file,
    seal_temporary_file,
)
from redactor.persistence.publication import publish_verified_artifact
from redactor.persistence.queue import claim_task, complete_task, recover_interrupted
from redactor.persistence.results import accepted_artifact, write_step_result
from redactor.schemas.persistence import Task
from redactor.schemas.verification import (
    VerificationCheck,
    VerificationContext,
    VerificationVerdict,
)
from redactor.utils.constants import (
    REQUIRED_VERIFICATION_CHECKS,
    STEP_PUBLISH,
    STEP_REWRITE,
    STEP_VERIFY,
)
from redactor.utils.errors import ERROR_VERIFICATION, ERROR_VERIFICATION_CONTEXT
from redactor.verification.verdict import conclude_verification


def prepare_verification(
    connection: sqlite3.Connection, source_file: Path
) -> tuple[Task, VerificationVerdict]:
    registered = register_file(connection, source_file, STEP_REWRITE, "v1")
    rewriting = claim_task(connection, step=STEP_REWRITE)
    assert rewriting is not None
    staged = create_temporary_file(connection, rewriting)
    staged.write_bytes(b"synthetic integration artifact\n")
    artifact = seal_temporary_file(connection, rewriting)
    complete_task(connection, rewriting, result=artifact)
    register_file(
        connection, source_file, STEP_VERIFY, "v1", dependencies=(registered.task_id,)
    )
    verifying = claim_task(connection, step=STEP_VERIFY)
    assert verifying is not None
    context = VerificationContext(
        original_sha256=registered.input_sha256,
        identity_sha256="0" * 64,
        policy_sha256="1" * 64,
    )
    checks = tuple(
        VerificationCheck.model_validate(
            {"kind": kind, "status": "pass", "expected": 1, "checked": 1}
        )
        for kind in REQUIRED_VERIFICATION_CHECKS
    )
    return verifying, conclude_verification(
        context, registered.task_id, artifact, checks
    )


def test_publication_rejects_forged_pass_and_mismatched_context(
    connection: sqlite3.Connection, source_file: Path
) -> None:
    verifying, verdict = prepare_verification(connection, source_file)
    # Dropping one mandatory check must not be hidden by a serialized pass flag.
    forged = verdict.model_copy(update={"checks": verdict.checks[:-1]})
    result = write_step_result(connection, verifying, forged)
    complete_task(connection, verifying, result=result)
    register_file(
        connection, source_file, STEP_PUBLISH, "v1", dependencies=(verifying.task_id,)
    )
    publishing = claim_task(connection, step=STEP_PUBLISH)
    assert publishing is not None
    with pytest.raises(ValueError, match=ERROR_VERIFICATION):
        publish_verified_artifact(
            connection, publishing, verifying.task_id, verdict.context
        )
    with pytest.raises(ValueError, match=ERROR_VERIFICATION_CONTEXT):
        publish_verified_artifact(
            connection,
            publishing,
            verifying.task_id,
            verdict.context.model_copy(update={"policy_sha256": "2" * 64}),
        )
    assert publishing.output_path is not None
    assert not publishing.output_path.exists()
    assert (
        connection.execute("SELECT count(*) FROM publication_intents").fetchone()[0]
        == 0
    )


def test_publication_reconciles_installed_bytes_after_sigkill(
    connection: sqlite3.Connection, source_file: Path
) -> None:
    verifying, verdict = prepare_verification(connection, source_file)
    result = write_step_result(connection, verifying, verdict)
    complete_task(connection, verifying, result=result)
    registered = register_file(
        connection, source_file, STEP_PUBLISH, "v1", dependencies=(verifying.task_id,)
    )
    crashed = subprocess.run(
        [
            sys.executable,
            str(Path(__file__).parent / "support" / "crash_after_publication.py"),
            str(state_directory(connection)),
            verifying.task_id,
        ],
        check=False,
        timeout=10,
    )
    assert crashed.returncode == -signal.SIGKILL
    assert registered.output_path is not None
    assert registered.output_path.read_bytes() == verdict.artifact.path.read_bytes()
    recover_interrupted(connection)
    publishing = claim_task(connection, step=STEP_PUBLISH)
    assert publishing is not None and publishing.attempt_count == 2
    published = publish_verified_artifact(
        connection, publishing, verifying.task_id, verdict.context
    )
    complete_task(connection, publishing, result=published)
    assert accepted_artifact(connection, publishing.task_id) == published
    assert (
        connection.execute("SELECT count(*) FROM publication_intents").fetchone()[0]
        == 1
    )


def test_verifier_unknown_and_failed_evidence_cannot_pass(
    connection: sqlite3.Connection, source_file: Path
) -> None:
    _, verdict = prepare_verification(connection, source_file)
    for changed_check in (
        verdict.checks[0].model_copy(update={"status": "unknown"}),
        verdict.checks[0].model_copy(update={"checked": 0, "unassessed": 1}),
        verdict.checks[0].model_copy(update={"status": "fail", "failed": 1}),
    ):
        changed = conclude_verification(
            verdict.context,
            verdict.producer_task_id,
            verdict.artifact,
            (changed_check, *verdict.checks[1:]),
        )
        assert changed.status != "pass"
    pixels_missing = conclude_verification(
        verdict.context.model_copy(update={"has_pixels": True}),
        verdict.producer_task_id,
        verdict.artifact,
        verdict.checks,
    )
    assert pixels_missing.status == "unknown"
