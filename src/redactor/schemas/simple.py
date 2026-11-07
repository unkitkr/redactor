"""In-memory values passed between the standalone experiment's functions."""

from pathlib import Path

from pydantic import BaseModel, Field

from redactor.schemas.formats import FileInspection
from redactor.schemas.native import NativeDocument
from redactor.schemas.pixels import EmbeddedImageEvidence, PixelFrame
from redactor.schemas.redaction import TextContext, TextEdit, TextFinding


class ExtractedFile(BaseModel, frozen=True, extra="forbid"):
    path: Path
    sha256: str
    inspection: FileInspection
    document: NativeDocument


class AnalyzedFile(BaseModel, frozen=True, extra="forbid"):
    source: ExtractedFile
    findings: tuple[tuple[tuple[TextFinding, ...], ...], ...]
    images: tuple[EmbeddedImageEvidence, ...] = ()
    frames: tuple[PixelFrame, ...] = ()


class RedactedFile(BaseModel, frozen=True, extra="forbid"):
    analysis: AnalyzedFile
    contexts: tuple[TextContext, ...]
    edits: tuple[tuple[tuple[TextEdit, ...], ...], ...]


class SimpleFileResult(BaseModel, frozen=True, extra="forbid"):
    input: str
    input_sha256: str = ""
    file_type: str = ""
    status: str
    stage: str
    reason: str | None = None
    exception_type: str | None = None
    output_sha256: str | None = None
    records: int = 0
    timings_seconds: dict[str, float] = Field(default_factory=dict)
