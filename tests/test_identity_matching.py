"""Resolve encrypted file evidence without joining conflicting or ambiguous people."""

import sqlite3
from datetime import date
from pathlib import Path

from redactor.identity.evidence import prepare_observation
from redactor.identity.matching import match_identity
from redactor.persistence.files.registration import register_file
from redactor.persistence.files.results import read_step_result, write_step_result
from redactor.persistence.queue.tasks import (
    claim_task,
    complete_task,
    recover_interrupted,
)
from redactor.schemas.identity import IdentityEvidence


def test_cross_file_aliases_require_corroboration_and_keep_roles_separate(
    connection: sqlite3.Connection, tmp_path: Path
) -> None:
    key = bytes(range(32))
    first = IdentityEvidence(
        role="patient",
        name="John Smith",
        identifier="00123",
        identifier_namespace="mrn",
        birth_date=date(1980, 1, 2),
        reference_date=date(2026, 3, 4),
        context_key="first-record",
    )
    evidence = (
        first,
        first.model_copy(update={"birth_date": date(1990, 1, 2)}),
        first.model_copy(update={"role": "provider", "identifier_namespace": "npi"}),
    )
    task_ids: list[str] = []
    for index, record in enumerate(evidence):
        source = tmp_path / f"file-{index}.txt"
        source.write_text("Synthetic document", encoding="utf-8")
        spec = register_file(connection, source, "analyze", "identity-test-v1")
        task_ids.append(spec.task_id)
        claimed = claim_task(connection)
        assert claimed is not None
        artifact = write_step_result(connection, claimed, record, encryption_key=key)
        assert b"John Smith" not in artifact.path.read_bytes()
        complete_task(connection, claimed, result=artifact)

    recover_interrupted(connection)
    candidates = tuple(
        prepare_observation(
            read_step_result(connection, task_id, IdentityEvidence, encryption_key=key),
            key,
        )
        for task_id in task_ids
    )
    assert len({candidate.observation_key for candidate in candidates}) == 3
    reversed_name = prepare_observation(
        first.model_copy(update={"name": "Smith, John", "context_key": "other-file"}),
        key,
    )
    assert reversed_name.observation_key == candidates[0].observation_key

    alias = prepare_observation(first.model_copy(update={"name": "J. Smith"}), key)
    resolved = match_identity(alias, candidates)
    assert resolved.status == "corroborated"
    assert resolved.identity_key == candidates[0].observation_key
    ambiguous = prepare_observation(
        alias.evidence.model_copy(update={"birth_date": None}), key
    )
    unresolved = match_identity(ambiguous, candidates)
    assert unresolved.status == "ambiguous"
    assert unresolved.identity_key == ambiguous.observation_key
    name_only = prepare_observation(
        first.model_copy(update={"identifier": "", "birth_date": None}), key
    )
    assert match_identity(name_only, candidates[:1]).status == "isolated"
    name_and_birth = prepare_observation(
        first.model_copy(update={"identifier": ""}), key
    )
    assert match_identity(name_and_birth, candidates).identity_key == (
        candidates[0].observation_key
    )
    contradictory = prepare_observation(
        alias.evidence.model_copy(update={"name": "J. Jones"}), key
    )
    assert match_identity(contradictory, candidates).status == "isolated"
    another_issuer = prepare_observation(
        alias.evidence.model_copy(update={"issuer": "another-system"}), key
    )
    assert match_identity(another_issuer, candidates).status == "isolated"
    # An unresolved name in a different record does not silently become one person.
    another_context = prepare_observation(
        name_only.evidence.model_copy(update={"context_key": "different-record"}), key
    )
    assert another_context.observation_key != name_only.observation_key


def test_middle_name_omission_links_anchors_without_bridging_conflicting_people() -> (
    None
):
    key = bytes(range(32))
    full = IdentityEvidence(
        role="patient",
        name="John Andrew Smith",
        identifier="123",
        identifier_namespace="mrn",
        birth_date=date(1970, 1, 1),
        context_key="full",
    )
    candidates = tuple(
        prepare_observation(full.model_copy(update={"name": name}), key)
        for name in (
            "John Andrew Smith",
            "John A. Smith",
            "John Smith",
        )
    )
    expected = min(candidate.observation_key for candidate in candidates)
    for candidate in candidates:
        assert match_identity(candidate, candidates).identity_key == expected
    conflicting = prepare_observation(
        full.model_copy(update={"name": "John Benjamin Smith"}), key
    )
    for candidate in (*candidates, conflicting):
        assert (
            match_identity(candidate, (*candidates, conflicting)).identity_key
            == candidate.observation_key
        )
    initial = prepare_observation(full.model_copy(update={"name": "J. Smith"}), key)
    assert match_identity(initial, (*candidates, conflicting)).status == "ambiguous"
