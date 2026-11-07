"""Evidence attached to the exact original, output and policy being verified."""

from collections.abc import Callable
from typing import Literal

from pydantic import BaseModel, Field, NonNegativeInt

from redactor.schemas.persistence import Artifact
from redactor.schemas.redaction import TextRange
from redactor.utils.constants import SHA256_PATTERN, VERIFIER_VERSION

VerificationStatus = Literal["pass", "fail", "unknown"]


class VerificationContext(BaseModel, frozen=True, extra="forbid"):
    original_sha256: str = Field(pattern=SHA256_PATTERN)
    identity_sha256: str = Field(pattern=SHA256_PATTERN)
    policy_sha256: str = Field(pattern=SHA256_PATTERN)
    verifier_version: str = VERIFIER_VERSION
    has_pixels: bool = False


class VerificationCheck(BaseModel, frozen=True, extra="forbid"):
    kind: Literal[
        "structure", "coverage", "transformations", "residual_phi", "clinical", "pixels"
    ]
    status: VerificationStatus
    expected: NonNegativeInt
    checked: NonNegativeInt
    failed: NonNegativeInt = 0
    unassessed: NonNegativeInt = 0
    reason_code: str | None = None


class VerificationVerdict(BaseModel, frozen=True, extra="forbid"):
    context: VerificationContext
    producer_task_id: str
    artifact: Artifact
    checks: tuple[VerificationCheck, ...]
    status: VerificationStatus
    judge_degradation: str | None = None


class ResidualCheck(BaseModel, frozen=True, extra="forbid"):
    """One bounded semantic check after exact byte and deterministic checks pass."""

    text: str
    statistical_text: str
    exemptions: tuple[TextRange, ...]
    allowed: tuple[TextRange, ...]


ResidualCheckCollector = Callable[[ResidualCheck], None]
