"""Commit bounded evidence batches and their input cursor in one transaction."""

import hmac
import sqlite3
from collections.abc import Iterator, Sequence

from redactor.identity.evidence import prepare_observation
from redactor.persistence.database import transaction
from redactor.persistence.queue.tasks import get_task, require_attempt
from redactor.policy.keys import derive_digest
from redactor.schemas.identity import (
    IdentityEvidence,
    IdentityObservation,
    IdentityScanProgress,
)
from redactor.schemas.persistence import Task
from redactor.utils.constants import (
    IDENTITY_BATCH_LIMIT,
    IDENTITY_BATCH_NAMESPACE,
    IDENTITY_STORAGE_CONTEXT,
    MAX_PRIVATE_RECORD_BYTES,
    STATUS_SUCCEEDED,
    STEP_ANALYZE,
)
from redactor.utils.encryption import decrypt_payload, encrypt_payload
from redactor.utils.errors import (
    ERROR_IDENTITY_EVIDENCE,
    ERROR_INVALID_CHECKPOINT,
    ERROR_RESOURCE_LIMIT,
    ERROR_STEP_RESULT,
)


def scan_progress(
    connection: sqlite3.Connection, task_id: str
) -> IdentityScanProgress | None:
    row = connection.execute(
        "SELECT sequence, input_offset, record_count, batch_digest "
        "FROM identity_scan_progress WHERE task_id = ?",
        (task_id,),
    ).fetchone()
    return IdentityScanProgress.model_validate(dict(row)) if row is not None else None


def save_observation_batch(
    connection: sqlite3.Connection,
    claimed: Task,
    evidence: Sequence[IdentityEvidence],
    key: bytes,
    *,
    sequence: int,
    input_offset: int,
    record_count: int,
) -> IdentityScanProgress:
    """The byte offset must end a complete native record, never a read buffer."""
    require_attempt(connection, claimed)
    if claimed.step != STEP_ANALYZE or len(evidence) > IDENTITY_BATCH_LIMIT:
        raise ValueError(ERROR_IDENTITY_EVIDENCE)
    digest = _batch_digest(evidence, key, claimed.task_id)
    progress = IdentityScanProgress(
        sequence=sequence,
        input_offset=input_offset,
        record_count=record_count,
        batch_digest=digest,
    )
    previous = scan_progress(connection, claimed.task_id)
    if previous == progress:
        return progress
    if (
        sequence != (previous.sequence + 1 if previous else 1)
        or input_offset > claimed.input_size
        or (previous is not None and input_offset <= previous.input_offset)
        or (previous is not None and record_count <= previous.record_count)
    ):
        raise ValueError(ERROR_INVALID_CHECKPOINT)

    # Normalize, merge and encrypt outside the write lock. Only the fenced owner
    # of this task may write its rows; the cursor is checked again inside the lock.
    observations: dict[str, IdentityObservation] = {}
    for item in evidence:
        observation = prepare_observation(item, key)
        existing = observations.get(observation.observation_key)
        observations[observation.observation_key] = (
            _merge(existing, observation) if existing is not None else observation
        )
    observation_keys = tuple(observations)
    maximum_parameters = connection.getlimit(sqlite3.SQLITE_LIMIT_VARIABLE_NUMBER) - 1
    for start in range(0, len(observation_keys), maximum_parameters):
        selected = observation_keys[start : start + maximum_parameters]
        parameters = ",".join("?" for _ in selected)
        rows = connection.execute(
            "SELECT observation_key, encrypted_payload FROM identity_observations "
            f"WHERE task_id = ? AND observation_key IN ({parameters})",
            (claimed.task_id, *selected),
        ).fetchall()
        for row in rows:
            context = _context(claimed.task_id, row["observation_key"])
            original = IdentityObservation.model_validate_json(
                decrypt_payload(key, row["encrypted_payload"], context=context)
            )
            observations[row["observation_key"]] = _merge(
                original, observations[row["observation_key"]]
            )
    prepared_rows = [
        (
            claimed.task_id,
            observation.observation_key,
            observation.identifier_key,
            observation.name_key,
            observation.birth_key,
            int(observation.is_anchor),
            encrypt_payload(
                key,
                observation.model_dump_json().encode(),
                context=_context(claimed.task_id, observation.observation_key),
            ),
        )
        for observation in observations.values()
    ]
    with transaction(connection):
        require_attempt(connection, claimed)
        if scan_progress(connection, claimed.task_id) != previous:
            raise ValueError(ERROR_INVALID_CHECKPOINT)
        connection.executemany(
            """
            INSERT INTO identity_observations (
                task_id, observation_key, identifier_key, name_key, birth_key,
                is_anchor, encrypted_payload
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(task_id, observation_key) DO UPDATE SET
                encrypted_payload = excluded.encrypted_payload
            """,
            prepared_rows,
        )
        connection.execute(
            """
            INSERT INTO identity_scan_progress (
                task_id, sequence, input_offset, record_count, batch_digest
            ) VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(task_id) DO UPDATE SET sequence = excluded.sequence,
                input_offset = excluded.input_offset,
                record_count = excluded.record_count,
                batch_digest = excluded.batch_digest
            """,
            (claimed.task_id, sequence, input_offset, record_count, digest),
        )
    return progress


def iter_observations(
    connection: sqlite3.Connection, task_id: str, key: bytes
) -> Iterator[IdentityObservation]:
    if get_task(connection, task_id).status != STATUS_SUCCEEDED:
        raise ValueError(ERROR_STEP_RESULT)
    cursor = connection.execute(
        "SELECT observation_key, encrypted_payload FROM identity_observations "
        "WHERE task_id = ? ORDER BY observation_key",
        (task_id,),
    )
    try:
        for row in cursor:
            payload = decrypt_payload(
                key,
                row["encrypted_payload"],
                context=_context(task_id, row["observation_key"]),
            )
            yield IdentityObservation.model_validate_json(payload)
    finally:
        cursor.close()


def _merge(
    first: IdentityObservation, second: IdentityObservation
) -> IdentityObservation:
    if first.observation_key != second.observation_key:
        raise ValueError(ERROR_IDENTITY_EVIDENCE)
    references = tuple(
        reference
        for reference in (first.evidence.reference_date, second.evidence.reference_date)
        if reference is not None
    )
    return first.model_copy(
        update={
            "evidence": first.evidence.model_copy(
                update={
                    "reference_date": max(references) if references else None,
                    "explicit_older_age": (
                        first.evidence.explicit_older_age
                        or second.evidence.explicit_older_age
                    ),
                }
            )
        }
    )


def _context(task_id: str, observation_key: str) -> bytes:
    return IDENTITY_STORAGE_CONTEXT.format(
        task_id=task_id, observation_key=observation_key
    ).encode()


def _batch_digest(
    evidence: Sequence[IdentityEvidence], key: bytes, task_id: str
) -> str:
    digest_key = derive_digest(key, task_id, namespace=IDENTITY_BATCH_NAMESPACE)
    digest = hmac.new(digest_key, digestmod="sha256")
    byte_count = 0
    for record in evidence:
        payload = record.model_dump_json().encode()
        byte_count += len(payload)
        if byte_count > MAX_PRIVATE_RECORD_BYTES:
            raise ValueError(ERROR_RESOURCE_LIMIT)
        digest.update(len(payload).to_bytes(8, "big"))
        digest.update(payload)
    return digest.hexdigest()
