"""Accepted terminal outcomes and PHI-free failure metadata."""

from typing import Literal

from pydantic import BaseModel

from redactor.schemas.persistence import Artifact


class FileFailure(BaseModel, frozen=True, extra="forbid"):
    step: str
    reason: str


class FileOutcome(BaseModel, frozen=True, extra="forbid"):
    status: Literal["published", "quarantined"]
    reason: str | None = None
    artifact: Artifact
