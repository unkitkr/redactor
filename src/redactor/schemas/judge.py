"""Hosted judge evidence, findings and the outcome envelope for publication."""

from typing import Literal, Self

from pydantic import BaseModel, Field, NonNegativeInt, PositiveInt, model_validator

from redactor.schemas.entities import EntityType
from redactor.schemas.provider import ModelReceipt
from redactor.schemas.redaction import TextRange
from redactor.schemas.verification import VerificationCheck
from redactor.utils.constants import (
    JUDGE_MAXIMUM_EVIDENCE_ITEMS,
    JUDGE_MAXIMUM_FINDINGS,
    JUDGE_MAXIMUM_IMAGES,
    JUDGE_MAXIMUM_ITEM_CHARACTERS,
    JUDGE_REFERENCE_PATTERN,
)
from redactor.utils.errors import ERROR_JUDGE_EVIDENCE

JudgeVerdict = Literal["leak", "likely_leak", "unsure", "clean"]


class JudgeImage(BaseModel, frozen=True, extra="forbid"):
    """One saved-output image frame; its pixels are the object under review."""

    reference: str = Field(pattern=JUDGE_REFERENCE_PATTERN)
    media_type: Literal["image/png", "image/jpeg", "image/tiff"]
    width: PositiveInt
    height: PositiveInt
    content_base64: str = Field(min_length=1)


class JudgeEvidenceItem(BaseModel, frozen=True, extra="forbid"):
    """Saved-output text plus the spans local checks already verified."""

    reference: str = Field(pattern=JUDGE_REFERENCE_PATTERN)
    text: str = Field(min_length=1, max_length=JUDGE_MAXIMUM_ITEM_CHARACTERS)
    verified_spans: tuple[TextRange, ...] = ()


class JudgeEvidence(BaseModel, frozen=True, extra="forbid"):
    """The summary submitted to the judge.

    It carries saved-output content and locally derived references only;
    original-input content beyond locally checked facts never enters it.
    Items, images and item length are bounded, and dropped entries are
    counted instead of hidden.
    """

    items: tuple[JudgeEvidenceItem, ...] = Field(
        default=(), max_length=JUDGE_MAXIMUM_EVIDENCE_ITEMS
    )
    images: tuple[JudgeImage, ...] = Field(default=(), max_length=JUDGE_MAXIMUM_IMAGES)
    omitted_items: NonNegativeInt = 0
    omitted_images: NonNegativeInt = 0


class JudgeFinding(BaseModel, frozen=True, extra="forbid"):
    """One per-item judgement; the reference must match sent evidence."""

    reference: str = Field(pattern=JUDGE_REFERENCE_PATTERN)
    verdict: JudgeVerdict
    entity_kind: EntityType


class JudgeAssessment(BaseModel, frozen=True, extra="forbid"):
    """The validated hosted response; no free-text reasoning is requested."""

    findings: tuple[JudgeFinding, ...] = Field(
        default=(), max_length=JUDGE_MAXIMUM_FINDINGS
    )


class JudgeDegradation(BaseModel, frozen=True, extra="forbid"):
    """Why the hosted judge could not complete; the local verdict stands."""

    reason_code: str


class JudgeOutcome(BaseModel, frozen=True, extra="forbid"):
    """Validated findings or a structured degradation, never both.

    The receipt carries the responding model and its token usage. An unsure
    finding is representable and fails closed at the caller.
    """

    findings: tuple[JudgeFinding, ...] = ()
    reason_code: str | None = None
    prompt_version: str = Field(min_length=1)
    receipt: ModelReceipt | None = None

    @model_validator(mode="after")
    def _findings_or_degradation(self) -> Self:
        if self.findings and self.reason_code is not None:
            raise ValueError(ERROR_JUDGE_EVIDENCE)
        return self


class JudgeApplication(BaseModel, frozen=True, extra="forbid"):
    """Checks with judge failures added, plus any degradation to record."""

    checks: tuple[VerificationCheck, ...]
    degradation: JudgeDegradation | None = None
