"""Interchangeable OCR functions that retain source-pixel coordinates."""

import csv
import io
import subprocess
from pathlib import Path
from typing import cast

from redactor.schemas.evaluation import OcrAdapter, OcrRegion
from redactor.utils.constants import (
    EVALUATION_OCR_TIMEOUT,
    EVALUATION_PPOCR_CLASSIFIER,
    EVALUATION_PPOCR_DETECTOR,
    EVALUATION_PPOCR_RECOGNIZERS,
)


def load_tesseract(directory: Path) -> OcrAdapter:
    def recognize(path: Path) -> tuple[OcrRegion, ...]:
        result = subprocess.run(
            [
                "tesseract",
                str(path),
                "stdout",
                "--tessdata-dir",
                str(directory),
                "-l",
                "eng",
                "--psm",
                "3",
                "-c",
                "tessedit_create_tsv=1",
            ],
            capture_output=True,
            text=True,
            check=True,
            timeout=EVALUATION_OCR_TIMEOUT,
        )
        regions = []
        for row in csv.DictReader(io.StringIO(result.stdout), delimiter="\t"):
            if row["level"] != "5" or not row["text"].strip():
                continue
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
        return tuple(regions)

    return recognize


def load_ppocr(directory: Path, language: str) -> OcrAdapter:
    from rapidocr import LangRec, ModelType, OCRVersion, RapidOCR
    from rapidocr.utils.output import RapidOCROutput

    recognizer = dict(EVALUATION_PPOCR_RECOGNIZERS)[language]
    engine = RapidOCR(
        params={
            "Det.model_path": str(directory / EVALUATION_PPOCR_DETECTOR),
            "Rec.model_path": str(directory / recognizer),
            "Cls.model_path": str(directory / EVALUATION_PPOCR_CLASSIFIER),
            "Det.ocr_version": OCRVersion.PPOCRV5,
            "Rec.ocr_version": OCRVersion.PPOCRV5,
            "Cls.ocr_version": OCRVersion.PPOCRV5,
            "Det.model_type": ModelType.MOBILE,
            "Rec.model_type": ModelType.MOBILE,
            "Rec.lang_type": LangRec.EN if language == "en" else LangRec.LATIN,
            "Det.mean": [0.485, 0.456, 0.406],
            "Det.std": [0.229, 0.224, 0.225],
            "Cls.cls_image_shape": [3, 80, 160],
            "EngineConfig.onnxruntime.intra_op_num_threads": 1,
            "EngineConfig.onnxruntime.inter_op_num_threads": 1,
            "Global.log_level": "error",
        }
    )

    def recognize(path: Path) -> tuple[OcrRegion, ...]:
        result = cast(RapidOCROutput, engine(str(path)))
        if result.txts is None or result.boxes is None:
            return ()
        return tuple(
            OcrRegion(
                text=text,
                box=(
                    float(box[:, 0].min()),
                    float(box[:, 1].min()),
                    float(box[:, 0].max()),
                    float(box[:, 1].max()),
                ),
            )
            for text, box in zip(result.txts, result.boxes, strict=True)
        )

    return recognize
