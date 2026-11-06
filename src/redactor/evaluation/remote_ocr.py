"""Hosted OCR shares the production reservation, retry and encrypted replay ledger."""

import sqlite3
from decimal import Decimal
from pathlib import Path

from redactor.evaluation.ocr_prompts import ocr_request
from redactor.evaluation.remote import recording_transport, remote_settings
from redactor.inference.ocr_evidence import read_ocr_image, validate_ocr_regions
from redactor.schemas.configuration import ResourceSettings
from redactor.schemas.ocr import OcrAdapter, OcrRegion, OcrResponse
from redactor.schemas.persistence import Task
from redactor.utils.constants import (
    EVALUATION_VISION_INPUT_BYTES,
    EVALUATION_VISION_INPUT_PRICE,
    EVALUATION_VISION_OUTPUT_PRICE,
    EVALUATION_VISION_OUTPUT_TOKENS,
    MODEL_KEY_ENVIRONMENT,
    MODEL_REMOTE,
    OCR_PNG_FORMAT,
)
from redactor.utils.errors import ERROR_MODEL_INPUT, ERROR_MODEL_RESPONSE
from redactor.utils.provider import request_json


def load_remote_ocr(
    connection: sqlite3.Connection,
    claimed: Task,
    model: str,
    mapping_key: bytes,
    api_key: str,
    receipt_path: Path,
    resources: ResourceSettings | None = None,
) -> OcrAdapter:
    limits = resources or ResourceSettings()
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
        try:
            content, size, image_format = read_ocr_image(
                path,
                maximum_bytes=min(
                    limits.max_native_file_bytes, EVALUATION_VISION_INPUT_BYTES
                ),
                maximum_pixels=limits.max_image_pixels,
            )
            # The evaluation image transport currently declares PNG explicitly.
            if image_format != OCR_PNG_FORMAT:
                raise ValueError(ERROR_MODEL_INPUT)
        except ValueError:
            raise ValueError(ERROR_MODEL_INPUT) from None
        request = ocr_request(content, size)
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
        try:
            regions = OcrResponse.model_validate(result.payload).regions
            return validate_ocr_regions(regions, size)
        except ValueError:
            raise ValueError(ERROR_MODEL_RESPONSE) from None

    return recognize
