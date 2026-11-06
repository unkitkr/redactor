"""Format inspection records; successful parsing never grants publication."""

from typing import Literal

from pydantic import BaseModel, NonNegativeInt

from redactor.schemas.tabular import CsvLayout

FileFormat = Literal[
    "unknown",
    "zip",
    "ole",
    "docx",
    "xlsx",
    "pdf",
    "dicom",
    "jpeg",
    "png",
    "tiff",
    "json",
    "fhir",
    "hl7",
    "csv",
    "tsv",
    "text",
]


class FileInspection(BaseModel, frozen=True, extra="forbid"):
    file_type: FileFormat
    reason: str | None = None
    encoding: str | None = None
    csv_layout: CsvLayout | None = None
    units: NonNegativeInt = 0
