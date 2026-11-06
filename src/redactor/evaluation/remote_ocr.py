"""Hosted OCR shares the production reservation, retry and encrypted replay ledger."""

import sqlite3
from decimal import Decimal
from pathlib import Path

from PIL import Image

from redactor.evaluation.ocr_prompts import ocr_request
from redactor.evaluation.remote import recording_transport, remote_settings
from redactor.schemas.evaluation import OcrAdapter, OcrRegion, OcrResponse
from redactor.schemas.persistence import Task
from redactor.utils.constants import (
    EVALUATION_VISION_INPUT_BYTES,
    EVALUATION_VISION_INPUT_PRICE,
    EVALUATION_VISION_OUTPUT_PRICE,
    EVALUATION_VISION_OUTPUT_TOKENS,
    MODEL_KEY_ENVIRONMENT,
    MODEL_REMOTE,
)
from redactor.utils.errors import ERROR_MODEL_RESPONSE
from redactor.utils.provider import request_json


def load_remote_ocr(
    connection: sqlite3.Connection,
    claimed: Task,
    model: str,
    mapping_key: bytes,
    api_key: str,
    receipt_path: Path,
) -> OcrAdapter:
    settings = remote_settings(model)
    remote = settings.remote.model_copy(
        update={
            "max_input_bytes": EVALUATION_VISION_INPUT_BYTES,
            "input_usd_per_million": Decimal(EVALUATION_VISION_INPUT_PRICE),
            "output_usd_per_million": Decimal(EVALUATION_VISION_OUTPUT_PRICE),
            "max_output_tokens": EVALUATION_VISION_OUTPUT_TOKENS,
        }
    )
    settings = settings.model_copy(update={"remote": remote})
    transport = recording_transport(receipt_path, remote)

    def recognize(path: Path) -> tuple[OcrRegion, ...]:
        request = ocr_request(path)
        result = request_json(
            connection,
            claimed,
            settings,
            request,
            OcrResponse,
            mapping_key,
            environment={MODEL_KEY_ENVIRONMENT: api_key},
            transport=transport,
        )
        if result.backend != MODEL_REMOTE:
            raise ValueError(result.reason_code or ERROR_MODEL_RESPONSE)
        regions = OcrResponse.model_validate(result.payload).regions
        with Image.open(path) as image:
            width, height = image.size
        for region in regions:
            left, top, right, bottom = region.box
            if not (0 <= left < right <= width and 0 <= top < bottom <= height):
                raise ValueError(ERROR_MODEL_RESPONSE)
        return regions

    return recognize
