"""Seal complete identity bindings and expose immutable, bounded worker lookups."""

import hmac
import json
import sqlite3
from contextlib import closing
from functools import lru_cache

from redactor.identity.cohorts import resolve_cohort
from redactor.persistence.files.results import read_step_result
from redactor.persistence.identities.resolution import (
    binding_digest,
    decode_cohort,
    resolution_progress,
)
from redactor.persistence.identities.sources import resolution_sources
from redactor.persistence.queue.tasks import get_task, require_attempt
from redactor.policy.keys import derive_digest
from redactor.schemas.identity import (
    IdentityLookup,
    IdentityMatch,
    IdentityRole,
    IdentitySnapshot,
    ResolvedIdentity,
)
from redactor.schemas.persistence import Task
from redactor.utils.constants import (
    IDENTITY_LOOKUP_CACHE_ENTRIES,
    IDENTITY_PATIENT,
    IDENTITY_PROVIDER,
    IDENTITY_SNAPSHOT_NAMESPACE,
    JSON_SEPARATORS,
    STEP_RESOLVE,
)
from redactor.utils.errors import ERROR_IDENTITY_SNAPSHOT


def build_identity_snapshot(
    connection: sqlite3.Connection,
    claimed: Task,
    key: bytes,
    maximum_date_shift_days: int,
) -> IdentitySnapshot:
    """Hash canonical private content, not randomized encryption envelopes."""
    require_attempt(connection, claimed)
    if claimed.step != STEP_RESOLVE:
        raise ValueError(ERROR_IDENTITY_SNAPSHOT)
    sources = resolution_sources(connection, claimed.task_id)
    expected = connection.execute(
        "SELECT count(*) FROM identity_observations AS observations "
        "JOIN identity_resolution_sources AS sources "
        "ON sources.source_task_id = observations.task_id "
        "WHERE sources.resolution_task_id = ?",
        (claimed.task_id,),
    ).fetchone()[0]
    digest = hmac.new(
        derive_digest(
            key, claimed.processing_version, namespace=IDENTITY_SNAPSHOT_NAMESPACE
        ),
        json.dumps(
            (maximum_date_shift_days, sources), separators=JSON_SEPARATORS
        ).encode(),
        digestmod="sha256",
    )
    observation_count = 0
    with closing(
        connection.execute(
            "SELECT source_task_id, observation_key, identity_key, status "
            "FROM identity_bindings WHERE resolution_task_id = ? "
            "ORDER BY source_task_id, observation_key",
            (claimed.task_id,),
        )
    ) as cursor:
        for row in cursor:
            payload = json.dumps(tuple(row), separators=JSON_SEPARATORS).encode()
            digest.update(len(payload).to_bytes(8, "big"))
            digest.update(payload)
            observation_count += 1
    if (
        expected != observation_count
        or expected
        != resolution_progress(connection, claimed.task_id).observation_count
    ):
        raise ValueError(ERROR_IDENTITY_SNAPSHOT)
    identity_count = 0
    reference_date = None
    with closing(
        connection.execute(
            "SELECT identity_key, encrypted_payload FROM identity_cohorts "
            "WHERE resolution_task_id = ? ORDER BY identity_key",
            (claimed.task_id,),
        )
    ) as cursor:
        for row in cursor:
            cohort = decode_cohort(key, claimed.task_id, row[0], row[1])
            if cohort.reference_date is not None:
                reference_date = max(
                    reference_date or cohort.reference_date, cohort.reference_date
                )
            payload = cohort.model_dump_json().encode()
            digest.update(len(payload).to_bytes(8, "big"))
            digest.update(payload)
            identity_count += 1
    return IdentitySnapshot(
        digest=digest.hexdigest(),
        source_count=len(sources),
        observation_count=observation_count,
        identity_count=identity_count,
        maximum_date_shift_days=maximum_date_shift_days,
        reference_date=reference_date,
    )


def load_identity_lookup(
    connection: sqlite3.Connection, task_id: str, key: bytes
) -> tuple[IdentitySnapshot, IdentityLookup]:
    """Open an accepted snapshot once; retain only a bounded cache of lookups."""
    if get_task(connection, task_id).step != STEP_RESOLVE:
        raise ValueError(ERROR_IDENTITY_SNAPSHOT)
    snapshot = read_step_result(
        connection, task_id, IdentitySnapshot, encryption_key=key
    )

    def read_identity(source_task_id: str, observation_key: str) -> ResolvedIdentity:
        row = connection.execute(
            "SELECT bindings.identity_key, bindings.status, bindings.binding_digest, "
            "cohorts.encrypted_payload FROM identity_bindings AS bindings "
            "JOIN identity_cohorts AS cohorts "
            "ON cohorts.resolution_task_id = bindings.resolution_task_id "
            "AND cohorts.identity_key = bindings.identity_key "
            "WHERE bindings.resolution_task_id = ? AND bindings.source_task_id = ? "
            "AND bindings.observation_key = ?",
            (task_id, source_task_id, observation_key),
        ).fetchone()
        if row is None:
            raise ValueError(ERROR_IDENTITY_SNAPSHOT)
        match = IdentityMatch(identity_key=row["identity_key"], status=row["status"])
        expected = binding_digest(key, task_id, source_task_id, observation_key, match)
        if not hmac.compare_digest(row["binding_digest"], expected):
            raise ValueError(ERROR_IDENTITY_SNAPSHOT)
        cohort = decode_cohort(
            key, task_id, match.identity_key, row["encrypted_payload"]
        )
        if cohort.reference_date is None:
            cohort = cohort.model_copy(
                update={"reference_date": snapshot.reference_date}
            )
        return resolve_cohort(cohort, match, key, snapshot.maximum_date_shift_days)

    patient_lookup = lru_cache(maxsize=IDENTITY_LOOKUP_CACHE_ENTRIES)(read_identity)
    provider_lookup = lru_cache(maxsize=IDENTITY_LOOKUP_CACHE_ENTRIES)(read_identity)
    other_lookup = lru_cache(maxsize=IDENTITY_LOOKUP_CACHE_ENTRIES)(read_identity)

    def lookup(
        source_task_id: str,
        observation_key: str,
        role: IdentityRole | None = None,
    ) -> ResolvedIdentity:
        if role == IDENTITY_PATIENT:
            return patient_lookup(source_task_id, observation_key)
        if role == IDENTITY_PROVIDER:
            return provider_lookup(source_task_id, observation_key)
        return other_lookup(source_task_id, observation_key)

    return snapshot, lookup
