"""Accepted analysis summaries, including rejected inputs that settle the barrier."""

from pydantic import BaseModel, Field, NonNegativeInt

from redactor.schemas.formats import FileFormat


class FileAnalysis(BaseModel, frozen=True, extra="forbid"):
    file_type: FileFormat
    record_count: NonNegativeInt
    reason: str | None = None
    counts: dict[str, NonNegativeInt] = Field(default_factory=dict)
