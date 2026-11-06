"""Stream all accepted observations through conservative matching and checkpoints."""

import sqlite3
from collections.abc import Iterable, Iterator

from redactor.persistence.identities.observations import iter_observations
from redactor.persistence.identities.resolution import (
    resolution_progress,
    resolve_batch,
)
from redactor.schemas.identity import IdentityObservation
from redactor.schemas.persistence import Task
from redactor.utils.constants import (
    IDENTITY_RESOLUTION_BATCH_SIZE,
    MAX_PRIVATE_RECORD_BYTES,
)
from redactor.utils.errors import ERROR_RESOURCE_LIMIT


def resolve_sources(
    connection: sqlite3.Connection,
    claimed: Task,
    sources: tuple[str, ...],
    key: bytes,
) -> None:
    progress = resolution_progress(connection, claimed.task_id)
    for source_task_id in sources:
        if source_task_id < progress.source_task_id:
            continue
        after_key = (
            progress.observation_key
            if source_task_id == progress.source_task_id
            else ""
        )
        observations = iter_observations(
            connection, source_task_id, key, after_key=after_key
        )
        for batch in _bounded_batches(observations):
            resolve_batch(connection, claimed, source_task_id, batch, key)


def _bounded_batches(
    observations: Iterable[IdentityObservation],
) -> Iterator[tuple[IdentityObservation, ...]]:
    batch: list[IdentityObservation] = []
    byte_count = 0
    for observation in observations:
        size = len(observation.model_dump_json().encode())
        if size > MAX_PRIVATE_RECORD_BYTES:
            raise ValueError(ERROR_RESOURCE_LIMIT)
        if batch and (
            len(batch) >= IDENTITY_RESOLUTION_BATCH_SIZE
            or byte_count + size > MAX_PRIVATE_RECORD_BYTES
        ):
            yield tuple(batch)
            batch.clear()
            byte_count = 0
        batch.append(observation)
        byte_count += size
    if batch:
        yield tuple(batch)
