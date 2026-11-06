"""Shift calendar dates while preserving their clock, timezone, and notation."""

import re
from datetime import date, datetime, timedelta

from redactor.policy.keys import derive_digest
from redactor.schemas.dates import ParsedDate
from redactor.utils.constants import (
    DATE_COMPACT_PATTERN,
    DATE_MDY_PATTERN,
    DATE_NAMED_DMY_PATTERN,
    DATE_NAMED_MDY_PATTERN,
    DATE_OFFSET_NAMESPACE,
    DATE_STYLE_COMPACT,
    DATE_STYLE_MDY,
    DATE_STYLE_NAMED_DMY,
    DATE_STYLE_NAMED_MDY,
    DATE_STYLE_YMD,
    DATE_YMD_PATTERN,
    MONTH_NAMES,
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
    for style, pattern in (
        (DATE_STYLE_NAMED_MDY, DATE_NAMED_MDY_PATTERN),
        (DATE_STYLE_NAMED_DMY, DATE_NAMED_DMY_PATTERN),
    ):
        match = re.fullmatch(pattern, value)
        if match is None:
            continue
        parts = match.groupdict()
        month = next(
            (
                index
                for index, name in enumerate(MONTH_NAMES, 1)
                if parts["month_name"].casefold()
                in (name.casefold(), name[:3].casefold())
            ),
            None,
        )
        if month is None:
            raise ValueError(ERROR_DATE)
        try:
            parsed = date(int(parts["year"]), month, int(parts["day"]))
            _validate_clock(parsed, parts["clock"], compact=False)
        except ValueError:
            raise ValueError(ERROR_DATE) from None
        return ParsedDate.model_validate(
            {
                "value": parsed,
                "style": style,
                "separator": parts["separator"],
                "day_width": len(parts["day"]),
                "clock": parts["clock"],
                "month_name": parts["month_name"],
                "year_separator": parts.get("year_separator", parts["separator"]),
            }
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
    if original.month_name:
        month = MONTH_NAMES[shifted.month - 1]
        if len(original.month_name) == 3:
            month = month[:3]
        if original.month_name.isupper():
            month = month.upper()
        elif original.month_name.islower():
            month = month.lower()
        if original.style == DATE_STYLE_NAMED_MDY:
            return (
                month
                + original.separator
                + day
                + original.year_separator
                + year
                + original.clock
            )
        return (
            day
            + original.separator
            + month
            + original.year_separator
            + year
            + original.clock
        )
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
