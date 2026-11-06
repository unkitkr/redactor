"""Native field policies and location-bound edits exchanged by pipeline steps."""

from typing import Literal

from pydantic import BaseModel, Field, NonNegativeInt

from redactor.schemas.identity import IdentityEvidence, ResolvedIdentity

FieldKind = Literal[
    "patient_name",
    "provider_name",
    "patient_id",
    "provider_id",
    "identifier",
    "birth_date",
    "date",
    "age",
    "phone",
    "email",
    "address",
    "zip",
    "lot",
    "clinical",
    "text",
    "location",
    "ssn",
    "relative_name",
    "person_name",
    "network",
    "web",
]


class ColumnPolicy(BaseModel, frozen=True, extra="forbid"):
    index: NonNegativeInt
    kind: FieldKind
    namespace: str = ""
    identifier_prefix: str = Field(default="", max_length=16, pattern=r"^[A-Za-z_]*$")
    supports_date_bounds: bool = True


class RowEvidence(BaseModel, frozen=True, extra="forbid"):
    patient: IdentityEvidence | None
    provider: IdentityEvidence | None


class RowIdentities(BaseModel, frozen=True, extra="forbid"):
    patient: ResolvedIdentity | None
    provider: ResolvedIdentity | None


class TextFinding(BaseModel, frozen=True, extra="forbid"):
    start: NonNegativeInt
    end: NonNegativeInt
    original: str
    kind: str = Field(min_length=1)
    namespace: str = ""


class TextEdit(TextFinding):
    replacement: str


class TextRange(BaseModel, frozen=True, extra="forbid"):
    start: NonNegativeInt
    end: NonNegativeInt


class TextContext(BaseModel, frozen=True, extra="forbid"):
    context_key: str
    patient_name: str = ""
    provider_name: str = ""
    patient: ResolvedIdentity | None = None
    provider: ResolvedIdentity | None = None
    maximum_date_shift_days: int
