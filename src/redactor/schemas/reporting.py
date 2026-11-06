"""Public reconciliation contains opaque references and aggregate evidence only."""

from typing import Literal

from pydantic import BaseModel, Field, NonNegativeInt


class FileReport(BaseModel, frozen=True, extra="forbid"):
    file_id: str
    input_sha256: str
    output_sha256: str
    actual_type: str
    status: Literal["published", "quarantined"]
    reason: str | None
    records: NonNegativeInt
    detected: dict[str, NonNegativeInt] = Field(default_factory=dict)
    applied: dict[str, NonNegativeInt] = Field(default_factory=dict)
    confirmed: dict[str, NonNegativeInt] = Field(default_factory=dict)
    duration_seconds: float = Field(ge=0)
    input_tokens: NonNegativeInt
    output_tokens: NonNegativeInt
    cost_bound_nanos: NonNegativeInt


class RunReport(BaseModel, frozen=True, extra="forbid"):
    run_id: str
    complete: bool
    inventoried: NonNegativeInt
    published: NonNegativeInt
    quarantined: NonNegativeInt
    files: tuple[FileReport, ...]
