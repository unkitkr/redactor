"""Accepted analysis summaries, including rejected inputs that settle the barrier."""

from pydantic import BaseModel, NonNegativeInt

from redactor.schemas.formats import FileFormat


class FileAnalysis(BaseModel, frozen=True, extra="forbid"):
    file_type: FileFormat
    record_count: NonNegativeInt
    reason: str | None = None
