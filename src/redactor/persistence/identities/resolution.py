"""Commit identity bindings, cohort evidence and resolution progress together."""

import json
import sqlite3
from collections.abc import Sequence
from contextlib import closing

from redactor.identity.cohorts import merge_cohorts
from redactor.identity.matching import match_identity
from redactor.persistence.database import transaction
from redactor.persistence.identities.sources import identity_candidates
from redactor.persistence.queue.tasks import require_attempt
from redactor.policy.keys import evidence_key
from redactor.schemas.identity import (
    IdentityCohort,
    IdentityMatch,
    IdentityObservation,
    IdentityResolutionProgress,
)
from redactor.schemas.persistence import Task
from redactor.utils.constants import (
    IDENTITY_BINDING_NAMESPACE,
    IDENTITY_COHORT_CONTEXT,
    IDENTITY_RESOLUTION_BATCH_SIZE,
    JSON_SEPARATORS,
    MAX_PRIVATE_RECORD_BYTES,
    STEP_RESOLVE,
)
from redactor.utils.encryption import decrypt_payload, encrypt_payload
from redactor.utils.errors import ERROR_IDENTITY_SNAPSHOT, ERROR_INVALID_CHECKPOINT


def resolution_progress(
    connection: sqlite3.Connection, task_id: str
) -> IdentityResolutionProgress:
    row = connection.execute(
        "SELECT source_task_id, observation_key, observation_count "
        "FROM identity_resolution_progress WHERE resolution_task_id = ?",
        (task_id,),
    ).fetchone()
    if row is None:
        raise ValueError(ERROR_IDENTITY_SNAPSHOT)
    return IdentityResolutionProgress.model_validate(dict(row))


def resolve_batch(
    connection: sqlite3.Connection,
    claimed: Task,
    source_task_id: str,
    observations: Sequence[IdentityObservation],
    key: bytes,
) -> None:
    require_attempt(connection, claimed)
    previous = resolution_progress(connection, claimed.task_id)
    if claimed.step != STEP_RESOLVE or not (
        0 < len(observations) <= IDENTITY_RESOLUTION_BATCH_SIZE
    ):
        raise ValueError(ERROR_IDENTITY_SNAPSHOT)
    previous_position = (previous.source_task_id, previous.observation_key)
    byte_count = 0
    matches: list[tuple[str, IdentityMatch]] = []
    cohorts: dict[str, IdentityCohort] = {}
    for observation in observations:
        position = (source_task_id, observation.observation_key)
        byte_count += len(observation.model_dump_json().encode())
        if position <= previous_position or byte_count > MAX_PRIVATE_RECORD_BYTES:
            raise ValueError(ERROR_INVALID_CHECKPOINT)
        previous_position = position
        with closing(
            identity_candidates(connection, claimed.task_id, observation, key)
        ) as (candidates):
            match = match_identity(observation, candidates)
        matches.append((observation.observation_key, match))
        cohort = IdentityCohort(
            identity_key=match.identity_key,
            birth_date=observation.evidence.birth_date,
            reference_date=observation.evidence.reference_date,
            explicit_older_age=observation.evidence.explicit_older_age,
            anchor_name=observation.evidence.name if observation.is_anchor else "",
            observed_name=observation.evidence.name,
        )
        existing = cohorts.get(match.identity_key)
        if existing is None:
            existing = read_cohort(connection, claimed.task_id, match.identity_key, key)
        cohorts[match.identity_key] = (
            merge_cohorts(existing, cohort) if existing is not None else cohort
        )
    prepared_cohorts = [
        (
            claimed.task_id,
            cohort.identity_key,
            encrypt_payload(
                key,
                cohort.model_dump_json().encode(),
                context=cohort_context(claimed.task_id, cohort.identity_key),
            ),
        )
        for cohort in cohorts.values()
    ]
    with transaction(connection):
        require_attempt(connection, claimed)
        if resolution_progress(connection, claimed.task_id) != previous:
            raise ValueError(ERROR_INVALID_CHECKPOINT)
        connection.executemany(
            "INSERT INTO identity_bindings (resolution_task_id, source_task_id, "
            "observation_key, identity_key, status, binding_digest) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                (
                    claimed.task_id,
                    source_task_id,
                    observation_key,
                    match.identity_key,
                    match.status,
                    binding_digest(
                        key, claimed.task_id, source_task_id, observation_key, match
                    ),
                )
                for observation_key, match in matches
            ),
        )
        connection.executemany(
            "INSERT INTO identity_cohorts "
            "(resolution_task_id, identity_key, encrypted_payload) VALUES (?, ?, ?) "
            "ON CONFLICT(resolution_task_id, identity_key) DO UPDATE SET "
            "encrypted_payload = excluded.encrypted_payload",
            prepared_cohorts,
        )
        connection.execute(
            "UPDATE identity_resolution_progress SET source_task_id = ?, "
            "observation_key = ?, observation_count = ? WHERE resolution_task_id = ?",
            (
                source_task_id,
                observations[-1].observation_key,
                previous.observation_count + len(observations),
                claimed.task_id,
            ),
        )


def read_cohort(
    connection: sqlite3.Connection, task_id: str, identity_key: str, key: bytes
) -> IdentityCohort | None:
    row = connection.execute(
        "SELECT encrypted_payload FROM identity_cohorts "
        "WHERE resolution_task_id = ? AND identity_key = ?",
        (task_id, identity_key),
    ).fetchone()
    if row is None:
        return None
    cohort = IdentityCohort.model_validate_json(
        decrypt_payload(key, row[0], context=cohort_context(task_id, identity_key))
    )
    if cohort.identity_key != identity_key:
        raise ValueError(ERROR_IDENTITY_SNAPSHOT)
    return cohort


def cohort_context(task_id: str, identity_key: str) -> bytes:
    return IDENTITY_COHORT_CONTEXT.format(
        task_id=task_id, identity_key=identity_key
    ).encode()


def binding_digest(
    key: bytes,
    task_id: str,
    source_task_id: str,
    observation_key: str,
    match: IdentityMatch,
) -> str:
    return evidence_key(
        key,
        json.dumps(
            (source_task_id, observation_key, match.identity_key, match.status),
            separators=JSON_SEPARATORS,
        ),
        namespace=IDENTITY_BINDING_NAMESPACE,
        scope=task_id,
    )
