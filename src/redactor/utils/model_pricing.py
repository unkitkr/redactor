"""Select configured prices and calculate conservative integer currency amounts."""

from decimal import ROUND_CEILING, Decimal

from redactor.schemas.configuration import PipelineSettings
from redactor.schemas.provider import ModelPricing, ModelRequest
from redactor.utils.constants import (
    MODEL_ENVELOPE_TOKENS,
    MODEL_PURPOSE_JUDGE,
    NANOS_PER_DOLLAR,
    TOKENS_PER_MILLION,
)
from redactor.utils.errors import ERROR_MODEL_CONFIGURATION, ERROR_MODEL_PRICING


def select_pricing(settings: PipelineSettings, request: ModelRequest) -> ModelPricing:
    if request.purpose == MODEL_PURPOSE_JUDGE:
        model = settings.verification.judge_model
        input_price = settings.verification.input_usd_per_million
        output_price = settings.verification.output_usd_per_million
    else:
        model = settings.remote.model
        input_price = settings.remote.input_usd_per_million
        output_price = settings.remote.output_usd_per_million
    if not model:
        raise ValueError(ERROR_MODEL_CONFIGURATION)
    if input_price is None or output_price is None:
        raise ValueError(ERROR_MODEL_PRICING)
    return ModelPricing(
        model=model,
        input_usd_per_million=input_price,
        output_usd_per_million=output_price,
    )


def currency_nanos(dollars: Decimal) -> int:
    return int((dollars * NANOS_PER_DOLLAR).to_integral_value(rounding=ROUND_CEILING))


def token_cost(pricing: ModelPricing, input_tokens: int, output_tokens: int) -> int:
    dollars = (
        input_tokens * pricing.input_usd_per_million
        + output_tokens * pricing.output_usd_per_million
    ) / TOKENS_PER_MILLION
    return currency_nanos(dollars)


def maximum_request_cost(
    pricing: ModelPricing, request: ModelRequest, output_tokens: int
) -> int:
    # Text BPE cannot have more content tokens than UTF-8 bytes. Reserve extra
    # protocol tokens instead of assuming one token for every four characters.
    input_bound = (
        len(request.system_prompt.encode())
        + len(request.input_text.encode())
        + MODEL_ENVELOPE_TOKENS
    )
    return token_cost(pricing, input_bound, output_tokens)
