"""Freeze eligible evidence sources and query candidates within that run only."""

import sqlite3
from collections.abc import Generator, Sequence

from redactor.persistence.database import transaction
from redactor.persistence.files.results import read_step_result
from redactor.persistence.identities.observations import (
    decode_observation,
    scan_progress,
)
from redactor.persistence.queue.tasks import get_task, require_attempt
from redactor.schemas.analysis import FileAnalysis
from redactor.schemas.identity import IdentityObservation
from redactor.schemas.persistence import Task
from redactor.utils.constants import STEP_ANALYZE, STEP_RESOLVE
from redactor.utils.errors import ERROR_IDENTITY_SNAPSHOT, ERROR_INCOMPLETE_INPUT


def initialize_resolution(
    connection: sqlite3.Connection,
    claimed: Task,
    analysis_task_ids: Sequence[str],
    key: bytes,
) -> tuple[str, ...]:
    """Rejected analysis results settle the barrier but never supply identity facts."""
    require_attempt(connection, claimed)
    dependencies = {
        row[0]
        for row in connection.execute(
            "SELECT depends_on FROM dependencies WHERE task_id = ?", (claimed.task_id,)
        )
    }
    if claimed.step != STEP_RESOLVE or dependencies != set(analysis_task_ids):
        raise ValueError(ERROR_IDENTITY_SNAPSHOT)
    accepted: list[str] = []
    for task_id in sorted(dependencies):
        source = get_task(connection, task_id)
        if source.step != STEP_ANALYZE or (
            source.processing_version != claimed.processing_version
        ):
            raise ValueError(ERROR_IDENTITY_SNAPSHOT)
        result = read_step_result(connection, task_id, FileAnalysis, encryption_key=key)
        if result.reason is not None:
            continue
        progress = scan_progress(connection, task_id)
        if progress is not None and (
            progress.input_offset != source.input_size
            or progress.record_count != result.record_count
        ):
            raise ValueError(ERROR_INCOMPLETE_INPUT)
        accepted.append(task_id)
    sources = tuple(accepted)
    with transaction(connection):
        require_attempt(connection, claimed)
        previous = connection.execute(
            "SELECT 1 FROM identity_resolution_progress WHERE resolution_task_id = ?",
            (claimed.task_id,),
        ).fetchone()
        if previous is not None:
            if resolution_sources(connection, claimed.task_id) != sources:
                raise ValueError(ERROR_IDENTITY_SNAPSHOT)
            return sources
        connection.executemany(
            "INSERT INTO identity_resolution_sources "
            "(resolution_task_id, source_task_id) VALUES (?, ?)",
            ((claimed.task_id, task_id) for task_id in sources),
        )
        connection.execute(
            "INSERT INTO identity_resolution_progress "
            "(resolution_task_id, source_task_id, observation_key, observation_count) "
            "VALUES (?, '', '', 0)",
            (claimed.task_id,),
        )
    return sources


def resolution_sources(connection: sqlite3.Connection, task_id: str) -> tuple[str, ...]:
    return tuple(
        row[0]
        for row in connection.execute(
            "SELECT source_task_id FROM identity_resolution_sources "
            "WHERE resolution_task_id = ? ORDER BY source_task_id",
            (task_id,),
        )
    )


def identity_candidates(
    connection: sqlite3.Connection,
    task_id: str,
    observation: IdentityObservation,
    key: bytes,
) -> Generator[IdentityObservation, None, None]:
    values: tuple[str, ...]
    if observation.identifier_key and (observation.name_key or observation.birth_key):
        condition = "observations.identifier_key = ?"
        values = (observation.identifier_key,)
        if observation.birth_key:
            condition += " AND observations.birth_key = ?"
            values += (observation.birth_key,)
    elif observation.name_key and observation.birth_key:
        condition = "observations.name_key = ? AND observations.birth_key = ?"
        values = (observation.name_key, observation.birth_key)
    else:
        return
    cursor = connection.execute(
        "SELECT observations.* FROM identity_observations AS observations "
        "JOIN identity_resolution_sources AS sources "
        "ON sources.source_task_id = observations.task_id "
        "WHERE sources.resolution_task_id = ? AND observations.is_anchor = 1 AND "
        + condition,
        (task_id, *values),
    )
    try:
        for row in cursor:
            yield decode_observation(
                key, row["task_id"], row["observation_key"], row["encrypted_payload"]
            )
    finally:
        cursor.close()
