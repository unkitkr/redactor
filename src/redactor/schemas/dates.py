"""Parsed date components with enough native spelling to write them back."""

from datetime import date
from typing import Literal

from pydantic import BaseModel, PositiveInt


class ParsedDate(BaseModel, frozen=True, extra="forbid"):
    value: date
    style: Literal["ymd", "mdy", "compact", "named_mdy", "named_dmy"]
    separator: str = ""
    month_width: PositiveInt = 2
    day_width: PositiveInt = 2
    year_width: Literal[2, 4] = 4
    clock: str = ""
    month_name: str = ""
    year_separator: str = " "
