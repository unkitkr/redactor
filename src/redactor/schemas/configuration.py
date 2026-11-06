"""Validated, secret-free settings shared by coordinator and workers."""

from decimal import Decimal
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, PositiveFloat, PositiveInt

from redactor.utils.constants import (
    DEFAULT_CHECKPOINT_RECORDS,
    DEFAULT_CHUNK_BYTES,
    DEFAULT_CIRCUIT_COOLDOWN_SECONDS,
    DEFAULT_CIRCUIT_FAILURES,
    DEFAULT_DATE_SHIFT_DAYS,
    DEFAULT_IMAGE_PIXELS,
    DEFAULT_MODEL_ATTEMPTS,
    DEFAULT_MODEL_BUDGET_USD,
    DEFAULT_MODEL_DEADLINE_SECONDS,
    DEFAULT_MODEL_INPUT_BYTES,
    DEFAULT_MODEL_OUTPUT_TOKENS,
    DEFAULT_MODEL_TIMEOUT_SECONDS,
    DEFAULT_NESTING_DEPTH,
    DEFAULT_OCR_LANGUAGE,
    DEFAULT_RECORD_BYTES,
    DEFAULT_SPACY_MODEL,
    MODEL_DIRECTORY,
    NER_SPACY,
    OCR_TESSERACT,
)


class RemoteSettings(BaseModel, frozen=True, extra="forbid"):
    enabled: bool = True
    base_url: str = ""
    model: str = ""
    vision: bool = False
    json_mode: bool = True
    budget_usd: Decimal = Field(default=Decimal(DEFAULT_MODEL_BUDGET_USD), ge=0)
    input_usd_per_million: Decimal | None = Field(default=None, ge=0)
    output_usd_per_million: Decimal | None = Field(default=None, ge=0)
    max_attempts: PositiveInt = DEFAULT_MODEL_ATTEMPTS
    timeout_seconds: PositiveFloat = DEFAULT_MODEL_TIMEOUT_SECONDS
    deadline_seconds: PositiveFloat = DEFAULT_MODEL_DEADLINE_SECONDS
    circuit_failures: PositiveInt = DEFAULT_CIRCUIT_FAILURES
    circuit_cooldown_seconds: PositiveFloat = DEFAULT_CIRCUIT_COOLDOWN_SECONDS
    max_output_tokens: PositiveInt = DEFAULT_MODEL_OUTPUT_TOKENS
    max_input_bytes: PositiveInt = DEFAULT_MODEL_INPUT_BYTES


class LocalSettings(BaseModel, frozen=True, extra="forbid"):
    ner: Literal["spacy", "gliner"] = NER_SPACY
    ocr: Literal["tesseract", "ppocr"] = OCR_TESSERACT
    spacy_model: str = DEFAULT_SPACY_MODEL
    ner_directory: Path | None = None
    ocr_directory: Path | None = None
    model_directory: Path = Path(MODEL_DIRECTORY)
    ocr_language: str = DEFAULT_OCR_LANGUAGE


class VerificationSettings(BaseModel, frozen=True, extra="forbid"):
    """Verification itself has no disable switch; only remote judging does."""

    judge_enabled: bool = True
    judge_model: str = ""
    judge_vision: bool = False
    input_usd_per_million: Decimal | None = Field(default=None, ge=0)
    output_usd_per_million: Decimal | None = Field(default=None, ge=0)


class ResourceSettings(BaseModel, frozen=True, extra="forbid"):
    max_record_bytes: PositiveInt = DEFAULT_RECORD_BYTES
    chunk_bytes: PositiveInt = DEFAULT_CHUNK_BYTES
    max_image_pixels: PositiveInt = DEFAULT_IMAGE_PIXELS
    max_nesting_depth: PositiveInt = DEFAULT_NESTING_DEPTH
    checkpoint_records: PositiveInt = DEFAULT_CHECKPOINT_RECORDS


class PolicySettings(BaseModel, frozen=True, extra="forbid"):
    maximum_date_shift_days: PositiveInt = DEFAULT_DATE_SHIFT_DAYS


class PipelineSettings(BaseModel, frozen=True, extra="forbid"):
    remote: RemoteSettings = Field(default_factory=RemoteSettings)
    local: LocalSettings = Field(default_factory=LocalSettings)
    verification: VerificationSettings = Field(default_factory=VerificationSettings)
    resources: ResourceSettings = Field(default_factory=ResourceSettings)
    policy: PolicySettings = Field(default_factory=PolicySettings)
