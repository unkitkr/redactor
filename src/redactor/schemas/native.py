"""Bounded records and locations exposed by native-format adapters."""

from pydantic import BaseModel

from redactor.schemas.redaction import ColumnPolicy


class NativeRecord(BaseModel, frozen=True, extra="forbid"):
    values: tuple[str, ...]
    policies: tuple[ColumnPolicy, ...]
    locations: tuple[tuple[str, ...], ...]


class NativeDocument(BaseModel, frozen=True, extra="forbid"):
    records: tuple[NativeRecord, ...]
