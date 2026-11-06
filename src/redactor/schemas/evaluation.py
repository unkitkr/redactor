"""Manually annotated synthetic examples and exact-span evaluation results."""

from pydantic import BaseModel, Field, NonNegativeInt, PositiveInt

from redactor.schemas.ocr import OcrRegion


class ReferenceMention(BaseModel, frozen=True, extra="forbid"):
    text: str = Field(min_length=1)
    kind: str = Field(min_length=1)
    occurrence: PositiveInt = 1


class TextExample(BaseModel, frozen=True, extra="forbid"):
    case_id: str = Field(min_length=1)
    text: str = Field(min_length=1)
    mentions: tuple[ReferenceMention, ...] = ()
    clinical: tuple[str, ...] = ()
    patient_name: str = ""
    provider_name: str = ""


class EvaluationSpan(BaseModel, frozen=True, extra="forbid"):
    start: NonNegativeInt
    end: PositiveInt
    kind: str


class DetectionCounts(BaseModel, frozen=True, extra="forbid"):
    true_positive: NonNegativeInt
    false_positive: NonNegativeInt
    false_negative: NonNegativeInt
    precision: float | None
    recall: float | None
    f1: float | None


class OcrReference(OcrRegion):
    sensitive: bool = True


class OcrExample(BaseModel, frozen=True, extra="forbid"):
    case_id: str
    image: str
    reference_text: str
    regions: tuple[OcrReference, ...]
