"""Match aliases only when independent identifiers or birth dates corroborate."""

from collections.abc import Iterable

from redactor.schemas.identity import IdentityMatch, IdentityObservation
from redactor.utils.constants import (
    IDENTITY_AMBIGUOUS,
    IDENTITY_CORROBORATED,
    IDENTITY_ISOLATED,
)


def match_identity(
    observation: IdentityObservation, candidates: Iterable[IdentityObservation]
) -> IdentityMatch:
    if observation.is_anchor:
        return IdentityMatch(
            identity_key=observation.observation_key, status=IDENTITY_CORROBORATED
        )
    matched_key: str | None = None
    for candidate in candidates:
        if not candidate.is_anchor or not _corroborates(observation, candidate):
            continue
        if matched_key is not None and matched_key != candidate.observation_key:
            return IdentityMatch(
                identity_key=observation.observation_key, status=IDENTITY_AMBIGUOUS
            )
        matched_key = candidate.observation_key
    return IdentityMatch(
        identity_key=matched_key or observation.observation_key,
        status=IDENTITY_CORROBORATED if matched_key else IDENTITY_ISOLATED,
    )


def _corroborates(left: IdentityObservation, right: IdentityObservation) -> bool:
    if left.evidence.role != right.evidence.role:
        return False
    if left.identifier_key and left.identifier_key != right.identifier_key:
        return False
    if left.birth_key and left.birth_key != right.birth_key:
        return False
    if left.evidence.name and not _compatible_names(
        left.evidence.name, right.evidence.name
    ):
        return False
    if left.identifier_key:
        return bool(left.name_key or left.birth_key)
    return bool(left.name_key and left.name_key == right.name_key and left.birth_key)


def _compatible_names(left: str, right: str) -> bool:
    if left == right:
        return True
    left_words, right_words = left.split(), right.split()
    if not (2 <= len(left_words) <= 3 and len(left_words) == len(right_words)):
        return False
    if left_words[-1] != right_words[-1]:
        return False
    return all(
        first == second
        or (len(first) == 1 and second.startswith(first))
        or (len(second) == 1 and first.startswith(second))
        for first, second in zip(left_words[:-1], right_words[:-1], strict=True)
    )
