"""OCR observations in original-image coordinates, never a coverage verdict."""

from collections.abc import Callable
from pathlib import Path

from pydantic import BaseModel, Field, FiniteFloat

from redactor.utils.constants import (
    OCR_MAXIMUM_REGION_CHARACTERS,
    OCR_MAXIMUM_REGIONS,
)


class OcrRegion(BaseModel, frozen=True, extra="forbid"):
    text: str = Field(min_length=1, max_length=OCR_MAXIMUM_REGION_CHARACTERS)
    box: tuple[FiniteFloat, FiniteFloat, FiniteFloat, FiniteFloat]


class OcrResponse(BaseModel, frozen=True, extra="forbid"):
    regions: tuple[OcrRegion, ...] = Field(max_length=OCR_MAXIMUM_REGIONS)


OcrAdapter = Callable[[Path], tuple[OcrRegion, ...]]
