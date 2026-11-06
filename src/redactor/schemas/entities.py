"""Character-bound model observations, not permission to redact or publish."""

from collections.abc import Callable
from typing import Literal

from pydantic import BaseModel, Field, NonNegativeInt, PositiveInt

from redactor.schemas.redaction import TextFinding, TextRange
from redactor.utils.constants import MAX_TEXT_ENTITIES

EntityType = Literal[
    "person", "organization", "location", "date", "time", "identifier", "contact", "age"
]


class TextEntity(BaseModel, frozen=True, extra="forbid"):
    start: NonNegativeInt
    end: PositiveInt
    text: str = Field(min_length=1)
    entity_type: EntityType
    label: str | None = Field(default=None, min_length=1, max_length=128)


class TextEntities(BaseModel, frozen=True, extra="forbid"):
    entities: tuple[TextEntity, ...] = Field(max_length=MAX_TEXT_ENTITIES)


class EntityDetection(TextEntities):
    """Detector observations and provenance, never a verification verdict."""

    backend: Literal["remote", "local"]
    fallback_reason: str | None = None


class PreparedTextAssessment(BaseModel, frozen=True, extra="forbid"):
    """Private deterministic evidence; no model state or publication verdict."""

    text: str
    patient_name: str = ""
    provider_name: str = ""
    findings: tuple[TextFinding, ...]
    protected: tuple[TextRange, ...]
    unresolved: tuple[TextRange, ...]


NerAdapter = Callable[[str], tuple[TextEntity, ...]]
NerBatchAdapter = Callable[[tuple[str, ...]], tuple[tuple[TextEntity, ...], ...]]
