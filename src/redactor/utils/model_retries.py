"""Capped exponential backoff with jitter and the server's minimum retry delay."""

import math
import random

from redactor.schemas.configuration import RemoteSettings


def retry_delay_seconds(
    settings: RemoteSettings, retry_index: int, retry_after_seconds: float
) -> float:
    """Index zero follows the first failure; Retry-After is never capped downward."""
    initial = min(settings.retry_initial_seconds, settings.retry_max_seconds)
    doublings_to_cap = math.ceil(
        math.log2(settings.retry_max_seconds) - math.log2(initial)
    )
    if retry_index >= doublings_to_cap:
        ceiling = settings.retry_max_seconds
    else:
        ceiling = math.ldexp(initial, retry_index)
    # Full jitter keeps workers from retrying together even after reaching the cap.
    return max(retry_after_seconds, random.uniform(0, ceiling))
