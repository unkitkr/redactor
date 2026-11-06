"""Validated contracts for the supported local model export families."""

from typing import Literal

from pydantic import BaseModel, Field

from redactor.utils.constants import GLINER_MAXIMUM_TOKENS


class GlinerConfiguration(BaseModel, frozen=True, extra="ignore", strict=True):
    """Only fields consumed by the pinned token-level adapter are authoritative."""

    span_mode: Literal["token_level"]
    max_len: int = Field(gt=0, le=GLINER_MAXIMUM_TOKENS)
    ent_token: str = Field(min_length=1)
    sep_token: str = Field(min_length=1)
