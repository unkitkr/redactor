"""Provider requests, persisted decisions and conservative usage accounting."""

from typing import Literal

from pydantic import BaseModel, Field, JsonValue, NonNegativeInt, PositiveInt


class ModelReservation(BaseModel, frozen=True, extra="forbid"):
    attempt_id: PositiveInt
    request_key: str
    reserved_nanos: NonNegativeInt


class ModelUsage(BaseModel, frozen=True, extra="forbid"):
    input_tokens: NonNegativeInt
    output_tokens: NonNegativeInt
    cost_nanos: NonNegativeInt


class ModelUnavailable(BaseModel, frozen=True, extra="forbid"):
    reason_code: str


class ModelDecision(BaseModel, frozen=True, extra="forbid"):
    backend: Literal["remote", "local"]
    payload: dict[str, JsonValue] | None = None
    reason_code: str | None = None


class ModelRequest(BaseModel, frozen=True, extra="forbid"):
    purpose: Literal["detector", "judge"]
    prompt_version: str = Field(min_length=1)
    system_prompt: str = Field(min_length=1)
    input_text: str
    context_id: str = Field(min_length=1)
