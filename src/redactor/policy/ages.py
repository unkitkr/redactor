"""Protect explicit and birth-date-derived ages at the ninety-year boundary."""

from datetime import date, timedelta

from redactor.policy.dates import parse_date, shift_date
from redactor.utils.constants import (
    AGE_GROUP_LABEL,
    AGE_GROUP_MINIMUM,
    BIRTH_BOUND_TEMPLATE,
)
from redactor.utils.errors import (
    ERROR_AGE,
    ERROR_AGE_REFERENCE,
    ERROR_AGE_REPRESENTATION,
)


def completed_years(birth_date: date, reference_date: date) -> int:
    """Use birthdays, not days divided by 365 or the machine's current date."""
    if birth_date > reference_date:
        raise ValueError(ERROR_AGE)
    birthday_not_reached = (reference_date.month, reference_date.day) < (
        birth_date.month,
        birth_date.day,
    )
    return reference_date.year - birth_date.year - int(birthday_not_reached)


def generalize_age(age: int) -> str:
    if age < 0:
        raise ValueError(ERROR_AGE)
    return AGE_GROUP_LABEL if age >= AGE_GROUP_MINIMUM else str(age)


def needs_birth_date_generalization(
    birth_date: date, reference_date: date, offset_days: int
) -> bool:
    """Also protect an age that crosses the boundary after calendar shifting."""
    original_age = completed_years(birth_date, reference_date)
    try:
        shifted_birth = birth_date + timedelta(days=offset_days)
        shifted_reference = reference_date + timedelta(days=offset_days)
    except OverflowError:
        raise ValueError(ERROR_AGE_REFERENCE) from None
    shifted_age = completed_years(shifted_birth, shifted_reference)
    return max(original_age, shifted_age) >= AGE_GROUP_MINIMUM


def replace_birth_date(
    value: str,
    offset_days: int,
    *,
    older_age_group: bool,
    cohort_reference: date | None,
    supports_bounds: bool,
) -> str:
    """The frozen identity snapshot supplies the same cohort decision to every file.

    A bound is suitable for text fields. Native date primitives need a format-aware
    representation; until one is available they must fail closed, not receive text
    that merely looks like a date. Clinical event dates still use the shared offset.
    """
    if not older_age_group:
        return shift_date(value, offset_days)
    parse_date(value)
    if cohort_reference is None:
        raise ValueError(ERROR_AGE_REFERENCE)
    if not supports_bounds:
        raise ValueError(ERROR_AGE_REPRESENTATION)
    try:
        reference = cohort_reference + timedelta(days=offset_days)
    except OverflowError:
        raise ValueError(ERROR_AGE_REFERENCE) from None
    year = reference.year - AGE_GROUP_MINIMUM
    if year < date.min.year:
        raise ValueError(ERROR_AGE_REFERENCE)
    return BIRTH_BOUND_TEMPLATE.format(year=year)
