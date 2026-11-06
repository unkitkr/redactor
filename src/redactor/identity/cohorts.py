"""Combine clinical references without joining people or consulting today's date."""

from redactor.policy.ages import needs_birth_date_generalization
from redactor.policy.dates import patient_date_offset
from redactor.schemas.identity import IdentityCohort, IdentityMatch, ResolvedIdentity
from redactor.utils.errors import ERROR_IDENTITY_EVIDENCE


def merge_cohorts(first: IdentityCohort, second: IdentityCohort) -> IdentityCohort:
    if first.identity_key != second.identity_key or (
        first.birth_date is not None
        and second.birth_date is not None
        and first.birth_date != second.birth_date
    ):
        raise ValueError(ERROR_IDENTITY_EVIDENCE)
    references = tuple(
        value
        for value in (first.reference_date, second.reference_date)
        if value is not None
    )
    return IdentityCohort(
        identity_key=first.identity_key,
        birth_date=first.birth_date or second.birth_date,
        reference_date=max(references) if references else None,
        explicit_older_age=first.explicit_older_age or second.explicit_older_age,
    )


def resolve_cohort(
    cohort: IdentityCohort,
    match: IdentityMatch,
    key: bytes,
    maximum_date_shift_days: int,
) -> ResolvedIdentity:
    if cohort.identity_key != match.identity_key:
        raise ValueError(ERROR_IDENTITY_EVIDENCE)
    offset = patient_date_offset(key, match.identity_key, maximum_date_shift_days)
    older_age: bool | None = None
    if cohort.explicit_older_age:
        older_age = True
    elif cohort.birth_date is not None and cohort.reference_date is not None:
        older_age = needs_birth_date_generalization(
            cohort.birth_date, cohort.reference_date, offset
        )
    return ResolvedIdentity(
        match=match,
        date_offset_days=offset,
        reference_date=cohort.reference_date,
        older_age_group=older_age,
    )
