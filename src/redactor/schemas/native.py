"""Bounded records and locations exposed by native-format adapters."""

from pydantic import BaseModel

from redactor.schemas.redaction import ColumnPolicy, RowEvidence


class NativeImage(BaseModel, frozen=True, extra="forbid"):
    location: tuple[str, ...]
    content: bytes


class NativeRecord(BaseModel, frozen=True, extra="forbid"):
    values: tuple[str, ...]
    policies: tuple[ColumnPolicy, ...]
    locations: tuple[tuple[str, ...], ...]
    evidence: RowEvidence | None = None
    context_scope: str = ""


class NativeDocument(BaseModel, frozen=True, extra="forbid"):
    records: tuple[NativeRecord, ...]
    images: tuple[NativeImage, ...] = ()
