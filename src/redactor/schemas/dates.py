"""Parsed date components with enough native spelling to write them back."""

from datetime import date
from typing import Literal

from pydantic import BaseModel, PositiveInt


class ParsedDate(BaseModel, frozen=True, extra="forbid"):
    value: date
    style: Literal["ymd", "mdy", "compact"]
    separator: str = ""
    month_width: PositiveInt = 2
    day_width: PositiveInt = 2
    clock: str = ""
