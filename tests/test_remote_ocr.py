"""Hosted OCR shares input and evidence limits without calling a paid endpoint."""

import json
from pathlib import Path

import httpx
import pytest
from PIL import Image

from redactor.evaluation import remote_ocr
from redactor.evaluation.state import evaluation_state
from redactor.schemas.configuration import ResourceSettings
from redactor.utils.errors import ERROR_MODEL_INPUT, ERROR_MODEL_RESPONSE


def test_remote_ocr_rejects_unbounded_images_and_unusable_cached_observations(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "image.png"
    Image.new("RGB", (100, 100), "white").save(source)
    calls = 0
    payload: dict[str, object] = {"regions": [{"text": "word", "box": [0, 0, 50, 30]}]}

    async def endpoint(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        model = json.loads(request.content)["model"]
        return httpx.Response(
            200,
            json={
                "id": "controlled-ocr",
                "object": "chat.completion",
                "created": 0,
                "model": model,
                "choices": [
                    {
                        "index": 0,
                        "finish_reason": "stop",
                        "message": {
                            "role": "assistant",
                            "content": json.dumps(payload),
                        },
                    }
                ],
                "usage": {
                    "prompt_tokens": 20,
                    "completion_tokens": 10,
                    "total_tokens": 30,
                },
            },
        )

    def transport(*_: object) -> httpx.MockTransport:
        return httpx.MockTransport(endpoint)

    monkeypatch.setattr(remote_ocr, "recording_transport", transport)
    with evaluation_state(tmp_path / "state", source, "analyze") as (
        connection,
        claimed,
        key,
    ):
        oversized = remote_ocr.load_remote_ocr(
            connection,
            claimed,
            "controlled-vision",
            key,
            "test-only",
            tmp_path / "receipts.jsonl",
            resources=ResourceSettings(max_native_file_bytes=10),
        )
        with pytest.raises(ValueError, match=ERROR_MODEL_INPUT):
            oversized(source)
        assert calls == 0
        adapter = remote_ocr.load_remote_ocr(
            connection,
            claimed,
            "controlled-vision",
            key,
            "test-only",
            tmp_path / "receipts.jsonl",
        )
        assert [region.text for region in adapter(source)] == ["word"]
        assert calls == 1
        invalid_payloads: tuple[dict[str, object], ...] = (
            {"regions": []},
            {"regions": [{"text": "word", "box": [0, 0, 101, 10]}]},
            {"regions": [{"text": " ", "box": [0, 0, 50, 10]}]},
            {"regions": [{"text": "word"}]},
        )
        for index, invalid in enumerate(invalid_payloads):
            payload = invalid
            invalid_adapter = remote_ocr.load_remote_ocr(
                connection,
                claimed,
                f"controlled-invalid-{index}",
                key,
                "test-only",
                tmp_path / "receipts.jsonl",
            )
            with pytest.raises(ValueError, match=ERROR_MODEL_RESPONSE):
                invalid_adapter(source)
            cached_calls = calls
            with pytest.raises(ValueError, match=ERROR_MODEL_RESPONSE):
                invalid_adapter(source)
            assert calls == cached_calls
