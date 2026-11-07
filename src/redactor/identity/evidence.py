"""Normalize evidence and derive opaque indexes without merging names alone."""

import json
from collections.abc import Callable
from functools import lru_cache

from redactor.policy.keys import evidence_key
from redactor.policy.normalization import normalize_identifier, normalize_name
from redactor.schemas.identity import IdentityEvidence, IdentityObservation
from redactor.utils.constants import (
    IDENTITY_BIRTH_NAMESPACE,
    IDENTITY_HASH_CACHE_ENTRIES,
    IDENTITY_HASH_CACHE_MAX_CHARACTERS,
    IDENTITY_IDENTIFIER_NAMESPACE,
    IDENTITY_LOOKUP_CACHE_ENTRIES,
    IDENTITY_NAME_NAMESPACE,
    IDENTITY_OBSERVATION_NAMESPACE,
    IDENTITY_PROVIDER,
    JSON_SEPARATORS,
)
from redactor.utils.errors import ERROR_IDENTITY_EVIDENCE


def prepare_observation(evidence: IdentityEvidence, key: bytes) -> IdentityObservation:
    return _prepare_observation(
        evidence,
        lambda value, namespace, scope: evidence_key(
            key, value, namespace=namespace, scope=scope
        ),
    )


def observation_preparer(
    key: bytes,
) -> Callable[[IdentityEvidence], IdentityObservation]:
    """Reuse keyed indexes within one bounded processing phase.

    Only immutable normalized index components are cached. Row context, clinical
    dates and older-age evidence always come from the current input record.
    """

    @lru_cache(maxsize=IDENTITY_HASH_CACHE_ENTRIES)
    def cached_index(value: str, namespace: str, scope: str) -> str:
        return evidence_key(key, value, namespace=namespace, scope=scope)

    @lru_cache(maxsize=IDENTITY_LOOKUP_CACHE_ENTRIES)
    def cached_observation_index(value: str, namespace: str, scope: str) -> str:
        return evidence_key(key, value, namespace=namespace, scope=scope)

    @lru_cache(maxsize=IDENTITY_LOOKUP_CACHE_ENTRIES)
    def cached_provider_index(value: str, namespace: str, scope: str) -> str:
        return evidence_key(key, value, namespace=namespace, scope=scope)

    def index(value: str, namespace: str, scope: str) -> str:
        component_size = len(value) + len(namespace) + len(scope)
        if component_size > IDENTITY_HASH_CACHE_MAX_CHARACTERS:
            return evidence_key(key, value, namespace=namespace, scope=scope)
        if namespace == IDENTITY_OBSERVATION_NAMESPACE:
            if scope == IDENTITY_PROVIDER:
                return cached_provider_index(value, namespace, scope)
            return cached_observation_index(value, namespace, scope)
        return cached_index(value, namespace, scope)

    def prepare(evidence: IdentityEvidence) -> IdentityObservation:
        return _prepare_observation(evidence, index)

    return prepare


def _prepare_observation(
    evidence: IdentityEvidence, index: Callable[[str, str, str], str]
) -> IdentityObservation:
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
        index(identifier, IDENTITY_IDENTIFIER_NAMESPACE, scope) if identifier else None
    )
    name_key = index(name, IDENTITY_NAME_NAMESPACE, evidence.role) if name else None
    birth_key = (
        index(
            evidence.birth_date.isoformat(),
            IDENTITY_BIRTH_NAMESPACE,
            evidence.role,
        )
        if evidence.birth_date is not None
        else None
    )
    observation_key = index(
        _encoded(
            (
                identifier_key,
                name_key,
                birth_key,
                None if is_anchor else evidence.context_key,
            )
        ),
        IDENTITY_OBSERVATION_NAMESPACE,
        evidence.role,
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
