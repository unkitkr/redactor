"""Private identity evidence and the result of conservative cross-file matching."""

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field, NonNegativeInt, PositiveInt

from redactor.utils.constants import SHA256_PATTERN

IdentityRole = Literal["patient", "provider", "relative"]


class IdentityEvidence(BaseModel, frozen=True, extra="forbid"):
    role: IdentityRole
    name: str = ""
    identifier: str = ""
    identifier_namespace: str = ""
    issuer: str = ""
    birth_date: date | None = None
    reference_date: date | None = None
    explicit_older_age: bool = False
    context_key: str = Field(min_length=1)


class IdentityObservation(BaseModel, frozen=True, extra="forbid"):
    observation_key: str = Field(pattern=SHA256_PATTERN)
    identifier_key: str | None
    name_key: str | None
    birth_key: str | None
    is_anchor: bool
    evidence: IdentityEvidence


class IdentityMatch(BaseModel, frozen=True, extra="forbid"):
    identity_key: str = Field(pattern=SHA256_PATTERN)
    status: Literal["corroborated", "isolated", "ambiguous"]


class IdentityScanProgress(BaseModel, frozen=True, extra="forbid"):
    sequence: PositiveInt
    input_offset: NonNegativeInt
    record_count: NonNegativeInt
    batch_digest: str = Field(pattern=SHA256_PATTERN)
