"""Pinned PP-OCRv5 CPU exports with local assets and complete output contracts."""

from pathlib import Path

import numpy as np

from redactor.inference.onnx import load_session
from redactor.schemas.ocr import OcrAdapter, OcrRegion
from redactor.utils.constants import (
    OCR_ENGLISH_LANGUAGES,
    OCR_MAXIMUM_REGIONS,
    ONNX_THREADS,
    PPOCR_CHARACTER_METADATA,
    PPOCR_CLASSIFIER,
    PPOCR_DETECTOR,
    PPOCR_ENGLISH_LANGUAGE,
    PPOCR_RECOGNIZERS,
)
from redactor.utils.errors import ERROR_LOCAL_INFERENCE, ERROR_LOCAL_UNAVAILABLE


def load_ppocr(directory: Path, language: str) -> OcrAdapter:
    try:
        from rapidocr import EngineType, LangRec, ModelType, OCRVersion, RapidOCR
        from rapidocr.utils.output import RapidOCROutput

        selected_language = (
            PPOCR_ENGLISH_LANGUAGE if language in OCR_ENGLISH_LANGUAGES else language
        )
        recognizer = dict(PPOCR_RECOGNIZERS)[selected_language]
        if not all(
            (directory / name).is_file()
            for name in (PPOCR_DETECTOR, PPOCR_CLASSIFIER, recognizer)
        ):
            raise ValueError(ERROR_LOCAL_UNAVAILABLE)
        # RapidOCR downloads a character dictionary if this metadata is missing,
        # even when explicit local weights were supplied. Reject that export.
        session = load_session(directory / recognizer)
        characters = session.get_modelmeta().custom_metadata_map.get(
            PPOCR_CHARACTER_METADATA
        )
        if not isinstance(characters, str) or not characters.strip():
            raise ValueError(ERROR_LOCAL_UNAVAILABLE)
        del session
        engine = RapidOCR(
            params={
                "Det.model_path": str(directory / PPOCR_DETECTOR),
                "Rec.model_path": str(directory / recognizer),
                "Cls.model_path": str(directory / PPOCR_CLASSIFIER),
                "Det.engine_type": EngineType.ONNXRUNTIME,
                "Rec.engine_type": EngineType.ONNXRUNTIME,
                "Cls.engine_type": EngineType.ONNXRUNTIME,
                "Det.ocr_version": OCRVersion.PPOCRV5,
                "Rec.ocr_version": OCRVersion.PPOCRV5,
                "Cls.ocr_version": OCRVersion.PPOCRV5,
                "Det.model_type": ModelType.MOBILE,
                "Rec.model_type": ModelType.MOBILE,
                "Rec.lang_type": (
                    LangRec.EN
                    if selected_language == PPOCR_ENGLISH_LANGUAGE
                    else LangRec.LATIN
                ),
                "Det.mean": [0.485, 0.456, 0.406],
                "Det.std": [0.229, 0.224, 0.225],
                "Cls.cls_image_shape": [3, 80, 160],
                "EngineConfig.onnxruntime.intra_op_num_threads": ONNX_THREADS,
                "EngineConfig.onnxruntime.inter_op_num_threads": ONNX_THREADS,
                "EngineConfig.onnxruntime.enable_cpu_mem_arena": False,
                "Global.log_level": "error",
            }
        )
    except Exception:
        raise ValueError(ERROR_LOCAL_UNAVAILABLE) from None

    def recognize(path: Path) -> tuple[OcrRegion, ...]:
        try:
            result = engine(str(path))
            # RapidOCR can swallow a failed stage and return an empty or partial
            # object. That is an inference failure, never a clean blank image.
            if (
                not isinstance(result, RapidOCROutput)
                or not result.txts
                or result.boxes is None
                or result.scores is None
                or not 0 < len(result.txts) <= OCR_MAXIMUM_REGIONS
            ):
                raise ValueError(ERROR_LOCAL_INFERENCE)
            boxes = np.asarray(result.boxes)
            confidences = np.asarray(result.scores)
            if (
                boxes.shape != (len(result.txts), 4, 2)
                or confidences.shape != (len(result.txts),)
                or not np.isfinite(boxes).all()
                or not np.isfinite(confidences).all()
                or np.any(confidences < 0)
                or np.any(confidences > 1)
            ):
                raise ValueError(ERROR_LOCAL_INFERENCE)
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
                for text, box in zip(result.txts, boxes, strict=True)
            )
        except Exception:
            raise ValueError(ERROR_LOCAL_INFERENCE) from None

    return recognize
