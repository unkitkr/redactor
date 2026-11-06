"""Shift calendar dates while preserving their clock, timezone, and notation."""

import re
from datetime import date, datetime, timedelta

from redactor.policy.keys import derive_digest
from redactor.schemas.dates import ParsedDate
from redactor.utils.constants import (
    DATE_COMPACT_PATTERN,
    DATE_MDY_PATTERN,
    DATE_OFFSET_NAMESPACE,
    DATE_STYLE_COMPACT,
    DATE_STYLE_MDY,
    DATE_STYLE_YMD,
    DATE_YMD_PATTERN,
)
from redactor.utils.errors import ERROR_DATE


def patient_date_offset(key: bytes, identity_key: str, maximum_days: int) -> int:
    if maximum_days < 1:
        raise ValueError(ERROR_DATE)
    digest = derive_digest(key, identity_key, namespace=DATE_OFFSET_NAMESPACE)
    selection = int.from_bytes(digest, "big") % (maximum_days * 2)
    return (
        -(selection + 1) if selection < maximum_days else selection - maximum_days + 1
    )


def parse_date(value: str) -> ParsedDate:
    """Only accept complete, valid dates; never invent a missing year or day."""
    for style, pattern in (
        (DATE_STYLE_YMD, DATE_YMD_PATTERN),
        (DATE_STYLE_MDY, DATE_MDY_PATTERN),
        (DATE_STYLE_COMPACT, DATE_COMPACT_PATTERN),
    ):
        match = re.fullmatch(pattern, value)
        if match is None:
            continue
        parts = match.groupdict()
        try:
            parsed = date(int(parts["year"]), int(parts["month"]), int(parts["day"]))
            clock = parts.get("clock") or ""
            _validate_clock(parsed, clock, compact=style == DATE_STYLE_COMPACT)
        except ValueError:
            raise ValueError(ERROR_DATE) from None
        return ParsedDate(
            value=parsed,
            style=style,
            separator=parts.get("separator") or "",
            month_width=len(parts["month"]),
            day_width=len(parts["day"]),
            clock=clock,
        )
    raise ValueError(ERROR_DATE)


def shift_date(value: str, offset_days: int) -> str:
    original = parse_date(value)
    try:
        shifted = original.value + timedelta(days=offset_days)
    except OverflowError:
        raise ValueError(ERROR_DATE) from None
    year = f"{shifted.year:04d}"
    month = f"{shifted.month:0{original.month_width}d}"
    day = f"{shifted.day:0{original.day_width}d}"
    if original.style == DATE_STYLE_MDY:
        components = (month, day, year)
    else:
        components = (year, month, day)
    return original.separator.join(components) + original.clock


def _validate_clock(value: date, clock: str, *, compact: bool) -> None:
    if not clock:
        return
    if compact:
        # Basic HL7/DICOM timestamps can stop at hours, minutes, or seconds.
        datetime.fromisoformat(value.isoformat() + "T" + clock)
    else:
        datetime.fromisoformat(value.isoformat() + clock)
