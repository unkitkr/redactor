"""Native CSV layout and complete-record resume positions."""

from typing import Literal

from pydantic import BaseModel, NonNegativeInt, PositiveInt


class CsvLayout(BaseModel, frozen=True, extra="forbid"):
    delimiter: Literal[",", "\t", ";"]
    line_ending: Literal["\n", "\r\n"]
    has_bom: bool
    columns: tuple[str, ...]
    header_end_offset: PositiveInt


class CsvRecord(BaseModel, frozen=True, extra="forbid"):
    number: PositiveInt
    values: tuple[str, ...]
    end_offset: NonNegativeInt
