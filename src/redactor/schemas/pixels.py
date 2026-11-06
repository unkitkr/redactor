"""Private pixel evidence shared by images and embedded native content."""

from collections.abc import Callable
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, NonNegativeInt, PositiveInt

from redactor.schemas.ocr import OcrRegion
from redactor.utils.constants import SHA256_PATTERN


class PixelMask(BaseModel, frozen=True, extra="forbid"):
    box: tuple[NonNegativeInt, NonNegativeInt, PositiveInt, PositiveInt]
    kind: Literal["text", "barcode", "face"]


class PixelFrame(BaseModel, frozen=True, extra="forbid"):
    width: PositiveInt
    height: PositiveInt
    sha256: str = Field(pattern=SHA256_PATTERN)
    regions: tuple[OcrRegion, ...]
    masks: tuple[PixelMask, ...]


PixelDetector = Callable[[Path], tuple[PixelMask, ...]]
