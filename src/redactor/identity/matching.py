"""Resolve compatible anchors without letting an omitted middle name bridge people."""

from collections.abc import Iterable

from redactor.policy.name_matching import compatible_name_spelling
from redactor.schemas.identity import IdentityMatch, IdentityObservation
from redactor.utils.constants import (
    IDENTITY_AMBIGUOUS,
    IDENTITY_CANDIDATE_LIMIT,
    IDENTITY_CORROBORATED,
    IDENTITY_ISOLATED,
)


def match_identity(
    observation: IdentityObservation, candidates: Iterable[IdentityObservation]
) -> IdentityMatch:
    pool: dict[str, IdentityObservation] = {}
    if observation.is_anchor:
        pool[observation.observation_key] = observation
    for number, candidate in enumerate(candidates, 1):
        if number > IDENTITY_CANDIDATE_LIMIT:
            return _unmatched(observation, ambiguous=True)
        if candidate.is_anchor and _evidence_compatible(observation, candidate):
            pool[candidate.observation_key] = candidate
    compatible = [
        candidate
        for candidate in pool.values()
        if _names_compatible(observation, candidate)
    ]
    if not compatible:
        return _unmatched(observation)
    # A missing middle name must not join both John A Smith and John B Smith.
    # Test the whole corroborated group, including the conflicting full form that
    # would otherwise be filtered out when matching either complete name.
    contenders = [
        candidate
        for candidate in pool.values()
        if any(_names_compatible(candidate, selected) for selected in compatible)
    ]
    first = compatible[0]
    conflict = any(
        not _evidence_compatible(left, right) or not _names_compatible(left, right)
        for index, left in enumerate(contenders)
        for right in contenders[index + 1 :]
    )
    if conflict:
        return _unmatched(observation, ambiguous=not observation.is_anchor)
    if any(
        candidate.identifier_key != first.identifier_key for candidate in compatible
    ):
        return _unmatched(observation, ambiguous=True)
    return IdentityMatch(
        identity_key=min(candidate.observation_key for candidate in compatible),
        status=IDENTITY_CORROBORATED,
    )


def _evidence_compatible(left: IdentityObservation, right: IdentityObservation) -> bool:
    if left.evidence.role != right.evidence.role:
        return False
    if left.identifier_key and left.identifier_key != right.identifier_key:
        return False
    if left.birth_key and left.birth_key != right.birth_key:
        return False
    if left.identifier_key:
        return bool(left.name_key or left.birth_key)
    return bool(left.name_key and left.birth_key)


def _names_compatible(left: IdentityObservation, right: IdentityObservation) -> bool:
    first, second = left.evidence.name, right.evidence.name
    if not first:
        return bool(left.identifier_key and left.birth_key)
    if not compatible_name_spelling(first, second):
        return False
    if not left.identifier_key:
        # Name plus DOB can corroborate a full spelling, not an initial.
        words = first.split()
        return len(words) >= 2 and len(words[0]) > 1 and len(words[-1]) > 1
    return True


def _unmatched(
    observation: IdentityObservation, *, ambiguous: bool = False
) -> IdentityMatch:
    return IdentityMatch(
        identity_key=observation.observation_key,
        status=IDENTITY_AMBIGUOUS
        if ambiguous
        else (IDENTITY_CORROBORATED if observation.is_anchor else IDENTITY_ISOLATED),
    )
