"""Run installed Tesseract and parse its bounded, original-pixel TSV output."""

import csv
import io
import math
import shutil
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory

from redactor.schemas.ocr import OcrAdapter, OcrRegion, OcrWord
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


def load_tesseract(
    directory: Path,
    language: str,
    *,
    word_boxes: bool = False,
    allow_empty: bool = False,
) -> OcrAdapter:
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
                return parse_tsv(
                    content.decode(TEXT_ENCODING),
                    word_boxes=word_boxes,
                    allow_empty=allow_empty,
                )
        except Exception:
            raise ValueError(ERROR_LOCAL_INFERENCE) from None

    return recognize


def parse_tsv(
    content: str, *, word_boxes: bool = False, allow_empty: bool = False
) -> tuple[OcrRegion, ...]:
    rows = csv.DictReader(io.StringIO(content), delimiter="\t")
    if rows.fieldnames != list(TESSERACT_TSV_FIELDS):
        raise ValueError(ERROR_LOCAL_INFERENCE)
    regions: list[OcrRegion] = []
    lines: dict[tuple[str, ...], list[OcrWord]] = {}
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
        line = tuple(
            row[name] for name in ("page_num", "block_num", "par_num", "line_num")
        )
        lines.setdefault(line, []).append(
            OcrWord(text=regions[-1].text, box=regions[-1].box)
        )
    if not regions and not allow_empty:
        raise ValueError(ERROR_LOCAL_INFERENCE)
    if word_boxes:
        return tuple(
            OcrRegion(
                text=" ".join(word.text for word in words),
                box=(
                    min(word.box[0] for word in words),
                    min(word.box[1] for word in words),
                    max(word.box[2] for word in words),
                    max(word.box[3] for word in words),
                ),
                words=tuple(words),
            )
            for words in lines.values()
        )
    return tuple(regions)
