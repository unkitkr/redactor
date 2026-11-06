"""Normalize evidence and derive opaque indexes without merging names alone."""

import json

from redactor.policy.keys import evidence_key
from redactor.policy.normalization import normalize_identifier, normalize_name
from redactor.schemas.identity import IdentityEvidence, IdentityObservation
from redactor.utils.constants import (
    IDENTITY_BIRTH_NAMESPACE,
    IDENTITY_IDENTIFIER_NAMESPACE,
    IDENTITY_NAME_NAMESPACE,
    IDENTITY_OBSERVATION_NAMESPACE,
    IDENTITY_PROVIDER,
    JSON_SEPARATORS,
)
from redactor.utils.errors import ERROR_IDENTITY_EVIDENCE


def prepare_observation(evidence: IdentityEvidence, key: bytes) -> IdentityObservation:
    name = normalize_name(evidence.name) if evidence.name.strip() else ""
    identifier = (
        normalize_identifier(evidence.identifier) if evidence.identifier else ""
    )
    if identifier and not evidence.identifier_namespace:
        raise ValueError(ERROR_IDENTITY_EVIDENCE)
    if not name and not identifier and evidence.birth_date is None:
        raise ValueError(ERROR_IDENTITY_EVIDENCE)
    normalized = evidence.model_copy(update={"name": name, "identifier": identifier})
    # A full name and corroborating identifier form an anchor. Patients also need
    # a birth date: the synthetic large-file family deliberately reuses MRNs.
    words = name.split()
    full_name = len(words) >= 2 and len(words[0]) > 1 and len(words[-1]) > 1
    is_anchor = bool(
        full_name
        and identifier
        and (evidence.role == IDENTITY_PROVIDER or evidence.birth_date is not None)
    )
    scope = _encoded((evidence.role, evidence.identifier_namespace, evidence.issuer))
    identifier_key = (
        evidence_key(
            key, identifier, namespace=IDENTITY_IDENTIFIER_NAMESPACE, scope=scope
        )
        if identifier
        else None
    )
    name_key = (
        evidence_key(key, name, namespace=IDENTITY_NAME_NAMESPACE, scope=evidence.role)
        if name
        else None
    )
    birth_key = (
        evidence_key(
            key,
            evidence.birth_date.isoformat(),
            namespace=IDENTITY_BIRTH_NAMESPACE,
            scope=evidence.role,
        )
        if evidence.birth_date is not None
        else None
    )
    observation_key = evidence_key(
        key,
        _encoded(
            (
                identifier_key,
                name_key,
                birth_key,
                None if is_anchor else evidence.context_key,
            )
        ),
        namespace=IDENTITY_OBSERVATION_NAMESPACE,
        scope=evidence.role,
    )
    return IdentityObservation(
        observation_key=observation_key,
        identifier_key=identifier_key,
        name_key=name_key,
        birth_key=birth_key,
        is_anchor=is_anchor,
        evidence=normalized,
    )


def _encoded(values: tuple[str | None, ...]) -> str:
    return json.dumps(values, separators=JSON_SEPARATORS, ensure_ascii=False)
