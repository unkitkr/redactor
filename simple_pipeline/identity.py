"""Resolve the small corpus in memory with the existing conservative match rules."""

from collections import defaultdict
from collections.abc import Iterable

from redactor.identity.cohorts import merge_cohorts, resolve_cohort
from redactor.identity.evidence import prepare_observation
from redactor.identity.matching import match_identity
from redactor.identity.native import native_evidence
from redactor.schemas.identity import (
    IdentityCohort,
    IdentityLookup,
    IdentityMatch,
    IdentityObservation,
    IdentityRole,
    ResolvedIdentity,
)
from redactor.schemas.simple import AnalyzedFile


def resolve_identities(
    files: Iterable[AnalyzedFile], key: bytes, maximum_date_shift_days: int
) -> IdentityLookup:
    observations: list[IdentityObservation] = []
    for file in files:
        for number, record in enumerate(file.source.document.records, 1):
            row = native_evidence(record, file.source.sha256, number)
            observations.extend(
                prepare_observation(person, key)
                for person in (row.patient, row.provider)
                if person is not None
            )

    by_identifier: dict[str, dict[str, IdentityObservation]] = defaultdict(dict)
    by_name_birth: dict[tuple[str, str], dict[str, IdentityObservation]] = defaultdict(
        dict
    )
    for observation in observations:
        if not observation.is_anchor:
            continue
        if observation.identifier_key:
            by_identifier[observation.identifier_key][observation.observation_key] = (
                observation
            )
        if observation.name_key and observation.birth_key:
            by_name_birth[(observation.name_key, observation.birth_key)][
                observation.observation_key
            ] = observation

    matches: dict[str, IdentityMatch] = {}
    cohorts: dict[str, IdentityCohort] = {}
    for observation in observations:
        candidates = (
            tuple(by_identifier.get(observation.identifier_key, {}).values())
            if observation.identifier_key
            else tuple(
                by_name_birth.get(
                    (observation.name_key or "", observation.birth_key or ""), {}
                ).values()
            )
        )
        if observation.birth_key:
            candidates = tuple(
                item for item in candidates if item.birth_key == observation.birth_key
            )
        match = match_identity(observation, candidates)
        matches[observation.observation_key] = match
        evidence = observation.evidence
        cohort = IdentityCohort(
            identity_key=match.identity_key,
            birth_date=evidence.birth_date,
            reference_date=evidence.reference_date,
            explicit_older_age=evidence.explicit_older_age,
            anchor_name=evidence.name if observation.is_anchor else "",
            observed_name=evidence.name,
            name_components=tuple(sorted(set(evidence.name.split()))),
        )
        previous = cohorts.get(match.identity_key)
        cohorts[match.identity_key] = (
            merge_cohorts(previous, cohort) if previous is not None else cohort
        )
    reference = max(
        (item.reference_date for item in cohorts.values() if item.reference_date),
        default=None,
    )
    resolved = {
        observation_key: resolve_cohort(
            cohorts[match.identity_key].model_copy(
                update={
                    "reference_date": cohorts[match.identity_key].reference_date
                    or reference
                }
            ),
            match,
            key,
            maximum_date_shift_days,
        )
        for observation_key, match in matches.items()
    }

    def lookup(
        source_task_id: str,
        observation_key: str,
        role: IdentityRole | None = None,
    ) -> ResolvedIdentity:
        return resolved[observation_key]

    return lookup
