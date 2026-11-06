"""OpenAI-compatible transport with bounded reads and no hidden SDK retries."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from urllib.parse import urlsplit

import httpx
from openai import AsyncOpenAI, omit
from openai.types.chat import ChatCompletion

from redactor.schemas.configuration import RemoteSettings
from redactor.schemas.provider import ModelRequest
from redactor.utils.constants import (
    HTTP_CONTENT_ENCODING_HEADER,
    HTTP_IDENTITY_ENCODING,
    MODEL_RESPONSE_BYTES,
)
from redactor.utils.errors import ERROR_MODEL_CONFIGURATION, ERROR_MODEL_RESPONSE


@asynccontextmanager
async def open_model_client(
    settings: RemoteSettings,
    api_key: str,
    transport: httpx.AsyncBaseTransport | None = None,
) -> AsyncGenerator[AsyncOpenAI, None]:
    endpoint = urlsplit(settings.base_url)
    if (
        endpoint.scheme not in ("https", "http")
        or not endpoint.hostname
        or endpoint.username is not None
        or endpoint.password is not None
        or endpoint.query
        or endpoint.fragment
    ):
        raise ValueError(ERROR_MODEL_CONFIGURATION)
    http_client = httpx.AsyncClient(
        transport=transport,
        follow_redirects=False,
        trust_env=False,
        event_hooks={"response": [_reject_http_error]},
    )
    async with AsyncOpenAI(
        base_url=settings.base_url,
        api_key=api_key,
        max_retries=0,
        default_headers={"Accept-Encoding": HTTP_IDENTITY_ENCODING},
        timeout=settings.timeout_seconds,
        http_client=http_client,
    ) as client:
        yield client


async def request_completion(
    client: AsyncOpenAI,
    settings: RemoteSettings,
    model: str,
    request: ModelRequest,
) -> ChatCompletion:
    async with client.chat.completions.with_streaming_response.create(
        model=model,
        messages=[
            {"role": "system", "content": request.system_prompt},
            {"role": "user", "content": request.input_text},
        ],
        max_tokens=settings.max_output_tokens,
        response_format={"type": "json_object"} if settings.json_mode else omit,
        stream=False,
    ) as response:
        payload = bytearray()
        async for chunk in response.iter_bytes():
            if len(payload) + len(chunk) > MODEL_RESPONSE_BYTES:
                raise ValueError(ERROR_MODEL_RESPONSE)
            payload.extend(chunk)
        try:
            return ChatCompletion.model_validate_json(payload, strict=True)
        except ValueError:
            raise ValueError(ERROR_MODEL_RESPONSE) from None


async def _reject_http_error(response: httpx.Response) -> None:
    """Prevent the SDK from buffering arbitrary error bodies before raising."""
    if not response.is_success:
        await response.aclose()
        raise httpx.HTTPStatusError(
            ERROR_MODEL_RESPONSE, request=response.request, response=response
        )
    if response.headers.get(HTTP_CONTENT_ENCODING_HEADER, HTTP_IDENTITY_ENCODING) != (
        HTTP_IDENTITY_ENCODING
    ):
        await response.aclose()
        raise ValueError(ERROR_MODEL_RESPONSE)
