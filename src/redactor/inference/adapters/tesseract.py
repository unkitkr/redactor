"""Run installed Tesseract and parse its bounded, original-pixel TSV output."""

import csv
import io
import math
import shutil
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory

from redactor.schemas.ocr import OcrAdapter, OcrRegion
from redactor.utils.constants import (
    OCR_ENGLISH_LANGUAGES,
    OCR_MAXIMUM_REGIONS,
    OCR_MAXIMUM_RESPONSE_BYTES,
    OCR_TESSERACT,
    OCR_TIMEOUT_SECONDS,
    TESSERACT_LANGUAGE,
    TESSERACT_LAYOUT_LEVELS,
    TESSERACT_MAXIMUM_CONFIDENCE,
    TESSERACT_OUTPUT_NAME,
    TESSERACT_OUTPUT_SUFFIX,
    TESSERACT_TRAINED_DATA,
    TESSERACT_TSV_FIELDS,
    TESSERACT_WORD_LEVEL,
    TEXT_ENCODING,
)
from redactor.utils.errors import ERROR_LOCAL_INFERENCE, ERROR_LOCAL_UNAVAILABLE


def load_tesseract(directory: Path, language: str) -> OcrAdapter:
    executable = shutil.which(OCR_TESSERACT)
    if (
        executable is None
        or language not in OCR_ENGLISH_LANGUAGES
        or not (directory / TESSERACT_TRAINED_DATA).is_file()
    ):
        raise ValueError(ERROR_LOCAL_UNAVAILABLE)

    def recognize(path: Path) -> tuple[OcrRegion, ...]:
        try:
            with TemporaryDirectory() as temporary:
                output = Path(temporary) / TESSERACT_OUTPUT_NAME
                subprocess.run(
                    [
                        executable,
                        str(path),
                        str(output),
                        "--tessdata-dir",
                        str(directory),
                        "-l",
                        TESSERACT_LANGUAGE,
                        "--psm",
                        "3",
                        "-c",
                        "tessedit_create_tsv=1",
                    ],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    check=True,
                    timeout=OCR_TIMEOUT_SECONDS,
                )
                with output.with_suffix(TESSERACT_OUTPUT_SUFFIX).open("rb") as stream:
                    content = stream.read(OCR_MAXIMUM_RESPONSE_BYTES + 1)
                if len(content) > OCR_MAXIMUM_RESPONSE_BYTES:
                    raise ValueError(ERROR_LOCAL_INFERENCE)
                return parse_tsv(content.decode(TEXT_ENCODING))
        except Exception:
            raise ValueError(ERROR_LOCAL_INFERENCE) from None

    return recognize


def parse_tsv(content: str) -> tuple[OcrRegion, ...]:
    rows = csv.DictReader(io.StringIO(content), delimiter="\t")
    if rows.fieldnames != list(TESSERACT_TSV_FIELDS):
        raise ValueError(ERROR_LOCAL_INFERENCE)
    regions: list[OcrRegion] = []
    for row in rows:
        if None in row or any(value is None for value in row.values()):
            raise ValueError(ERROR_LOCAL_INFERENCE)
        if row["level"] in TESSERACT_LAYOUT_LEVELS and not row["text"].strip():
            continue
        confidence = float(row["conf"])
        if (
            row["level"] != TESSERACT_WORD_LEVEL
            or not row["text"].strip()
            or not math.isfinite(confidence)
            or not 0 <= confidence <= TESSERACT_MAXIMUM_CONFIDENCE
            or len(regions) >= OCR_MAXIMUM_REGIONS
        ):
            raise ValueError(ERROR_LOCAL_INFERENCE)
        left, top = float(row["left"]), float(row["top"])
        regions.append(
            OcrRegion(
                text=row["text"],
                box=(
                    left,
                    top,
                    left + float(row["width"]),
                    top + float(row["height"]),
                ),
            )
        )
    if not regions:
        raise ValueError(ERROR_LOCAL_INFERENCE)
    return tuple(regions)
