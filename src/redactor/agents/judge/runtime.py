"""Transport glue for vision judging; text judging reuses the shared transport.

Image-bearing judge requests embed saved frames as base64 inside the user
JSON. The wrapper rewrites that field into multimodal content parts and then
forwards through the supplied transport, or the real network when none is
supplied, exactly like the evaluation recorder.
"""

import json

import httpx

from redactor.schemas.judge import JudgeEvidence
from redactor.utils.constants import (
    JSON_SEPARATORS,
    JUDGE_IMAGE_FIELD,
    MODEL_RESPONSE_BYTES,
)
from redactor.utils.errors import ERROR_MODEL_RESPONSE


def vision_transport(inner: httpx.AsyncBaseTransport | None) -> httpx.MockTransport:
    """Forward judge requests with their image field as content parts."""

    async def forward(request: httpx.Request) -> httpx.Response:
        forwarded = _with_image_parts(request)
        if inner is None:
            async with httpx.AsyncHTTPTransport(retries=0) as network:
                return await _relay(network, forwarded)
        return await _relay(inner, forwarded)

    return httpx.MockTransport(forward)


def _with_image_parts(request: httpx.Request) -> httpx.Request:
    """Return a rewritten request, or the original when it carries no images."""
    try:
        payload = json.loads(request.content)
        content = payload["messages"][1]["content"]
        user = json.loads(content)
        evidence = JudgeEvidence.model_validate(user)
    except (KeyError, IndexError, TypeError, ValueError):
        return request
    if not evidence.images:
        return request
    remaining = {key: value for key, value in user.items() if key != JUDGE_IMAGE_FIELD}
    parts: list[dict[str, object]] = [
        {
            "type": "text",
            "text": json.dumps(
                remaining, ensure_ascii=False, separators=JSON_SEPARATORS
            ),
        }
    ]
    for image in evidence.images:
        parts.append(
            {
                "type": "image_url",
                "image_url": {
                    "url": f"data:{image.media_type};base64,{image.content_base64}"
                },
            }
        )
    payload["messages"][1]["content"] = parts
    body = json.dumps(payload, ensure_ascii=False).encode()
    headers = dict(request.headers)
    headers["content-length"] = str(len(body))
    return httpx.Request(request.method, request.url, headers=headers, content=body)


async def _relay(
    transport: httpx.AsyncBaseTransport, request: httpx.Request
) -> httpx.Response:
    """Buffer one bounded response so the delegate transport can close early."""
    response = await transport.handle_async_request(request)
    body = bytearray()
    try:
        async for chunk in response.aiter_bytes():
            if len(body) + len(chunk) > MODEL_RESPONSE_BYTES:
                raise ValueError(ERROR_MODEL_RESPONSE)
            body.extend(chunk)
    finally:
        await response.aclose()
    return httpx.Response(
        response.status_code, headers=response.headers, content=bytes(body)
    )
