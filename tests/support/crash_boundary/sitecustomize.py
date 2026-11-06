"""Test-only SIGKILL injection; production code and model bytes stay unchanged."""

import os
import signal
import sqlite3
from collections.abc import Mapping, Sequence
from pathlib import Path


def install_crash_boundary() -> None:
    boundary = os.environ.get("REDACTOR_TEST_CRASH_BOUNDARY")
    if boundary is None:
        return

    from redactor.persistence.files import checkpoints
    from redactor.persistence.identities import observations
    from redactor.schemas.identity import IdentityEvidence, IdentityScanProgress
    from redactor.schemas.persistence import Checkpoint, Task
    from redactor.schemas.pipeline import StepHandler, StepResult
    from redactor.workers import pipeline

    marker = Path(os.environ["REDACTOR_TEST_CRASH_MARKER"])

    def crash_once() -> None:
        try:
            with marker.open("xb") as stream:
                stream.write(boundary.encode())
                stream.flush()
                os.fsync(stream.fileno())
        except FileExistsError:
            return
        os.kill(os.getpid(), signal.SIGKILL)

    if boundary == "analysis_checkpoint":
        save_observations = observations.save_observation_batch

        def save_batch(
            connection: sqlite3.Connection,
            claimed: Task,
            evidence: Sequence[IdentityEvidence],
            key: bytes,
            *,
            sequence: int,
            input_offset: int,
            record_count: int,
            counts: dict[str, int] | None = None,
        ) -> IdentityScanProgress:
            result = save_observations(
                connection,
                claimed,
                evidence,
                key,
                sequence=sequence,
                input_offset=input_offset,
                record_count=record_count,
                counts=counts,
            )
            crash_once()
            return result

        observations.save_observation_batch = save_batch
    elif boundary == "rewrite_checkpoint":
        save_checkpoint = checkpoints.save_checkpoint

        def save_output(
            connection: sqlite3.Connection, claimed: Task, checkpoint: Checkpoint
        ) -> None:
            save_checkpoint(connection, claimed, checkpoint)
            # Simulate a partially written following record as well.
            with checkpoint.artifact_path.open("ab") as stream:
                stream.write(b'"uncommitted suffix')
                stream.flush()
                os.fsync(stream.fileno())
            crash_once()

        checkpoints.save_checkpoint = save_output
    else:
        execute_task = pipeline.execute_task

        def execute(
            connection: sqlite3.Connection,
            task: Task,
            handlers: Mapping[str, StepHandler],
        ) -> None:
            if task.step != boundary:
                execute_task(connection, task, handlers)
                return
            handler = handlers[task.step]

            def finish_step(connection: sqlite3.Connection, task: Task) -> StepResult:
                result = handler(connection, task)
                crash_once()
                return result

            execute_task(connection, task, {**handlers, task.step: finish_step})

        pipeline.execute_task = execute


install_crash_boundary()
