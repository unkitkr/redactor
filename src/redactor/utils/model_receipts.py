"""Extract endpoint attribution and conservatively account for reported charges."""

from decimal import Decimal, InvalidOperation

from openai.types.chat import ChatCompletion

from redactor.schemas.provider import ModelPricing, ModelReceipt, ModelUsage
from redactor.utils.errors import ERROR_MODEL_RESPONSE
from redactor.utils.model_pricing import currency_nanos, token_cost


def completion_receipt(
    completion: ChatCompletion, pricing: ModelPricing
) -> ModelReceipt:
    usage = completion.usage
    reported_cost = None
    if usage is not None:
        cost = (usage.model_extra or {}).get("cost")
        if cost is not None:
            try:
                reported_cost = Decimal(str(cost))
            except InvalidOperation:
                raise ValueError(ERROR_MODEL_RESPONSE) from None
            if not reported_cost.is_finite() or reported_cost < 0:
                raise ValueError(ERROR_MODEL_RESPONSE)
    provider = (completion.model_extra or {}).get("provider")
    # Validate Decimal magnitude before accounting converts it to an integer;
    # even a short exponent string can otherwise demand an enormous allocation.
    return ModelReceipt(
        requested_model=pricing.model,
        returned_model=completion.model,
        provider=provider if isinstance(provider, str) else None,
        input_tokens=usage.prompt_tokens if usage is not None else None,
        output_tokens=usage.completion_tokens if usage is not None else None,
        reported_cost_usd=reported_cost,
    )


def accounted_usage(receipt: ModelReceipt, pricing: ModelPricing) -> ModelUsage | None:
    """Lower endpoint charges cannot reduce our configured token-rate accounting."""
    if receipt.input_tokens is None or receipt.output_tokens is None:
        return None
    cost = token_cost(pricing, receipt.input_tokens, receipt.output_tokens)
    if receipt.reported_cost_usd is not None:
        cost = max(cost, currency_nanos(receipt.reported_cost_usd))
    return ModelUsage(
        input_tokens=receipt.input_tokens,
        output_tokens=receipt.output_tokens,
        cost_nanos=cost,
    )
