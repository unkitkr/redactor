"""Provider requests, persisted decisions and conservative usage accounting."""

from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field, JsonValue, NonNegativeInt, PositiveInt


class ModelReservation(BaseModel, frozen=True, extra="forbid"):
    attempt_id: PositiveInt
    attempt_number: PositiveInt
    request_key: str
    reserved_nanos: NonNegativeInt


class ModelUsage(BaseModel, frozen=True, extra="forbid"):
    input_tokens: NonNegativeInt
    output_tokens: NonNegativeInt
    cost_nanos: NonNegativeInt


class ModelUnavailable(BaseModel, frozen=True, extra="forbid"):
    reason_code: str


class ModelReceipt(BaseModel, frozen=True, extra="forbid"):
    """Endpoint attribution kept with the encrypted response, without source text."""

    requested_model: str
    returned_model: str
    provider: str | None = None
    input_tokens: NonNegativeInt | None = None
    output_tokens: NonNegativeInt | None = None
    reported_cost_usd: Decimal | None = Field(default=None, ge=0)


class ModelDecision(BaseModel, frozen=True, extra="forbid"):
    backend: Literal["remote", "local"]
    payload: dict[str, JsonValue] | None = None
    reason_code: str | None = None
    receipt: ModelReceipt | None = None


class ModelRequest(BaseModel, frozen=True, extra="forbid"):
    purpose: Literal["detector", "judge"]
    prompt_version: str = Field(min_length=1)
    system_prompt: str = Field(min_length=1)
    input_text: str
    context_id: str = Field(min_length=1)


class ModelPricing(BaseModel, frozen=True, extra="forbid"):
    model: str = Field(min_length=1)
    input_usd_per_million: Decimal = Field(ge=0)
    output_usd_per_million: Decimal = Field(ge=0)


class ModelFailure(BaseModel, frozen=True, extra="forbid"):
    reason_code: str
    retry_after_seconds: float = Field(default=0, ge=0)


class ModelRequestWindow(BaseModel, frozen=True, extra="forbid"):
    deadline_at: float = Field(ge=0, allow_inf_nan=False)
    retry_after_at: float = Field(default=0, ge=0)
    attempts_used: NonNegativeInt = 0
