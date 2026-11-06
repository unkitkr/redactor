"""Allowlisted model labels and measurement context, never arbitrary report text."""

import re

from redactor.utils.constants import SHA256_PATTERN


def filename_model(source: str) -> str:
    name = (
        source.rsplit("/", maxsplit=1)[-1]
        .removesuffix(".json")
        .removesuffix("-container")
    )
    labels = {
        "dashboard-overhead": "Local dashboard",
        "tesseract-fast": "Tesseract eng fast",
        "tesseract-best": "Tesseract eng best",
        "ppocr-en": "PP-OCRv5 mobile English",
        "ppocr-latin": "PP-OCRv5 mobile Latin",
        "deepseek-flash-vision": "deepseek/deepseek-v4.1-flash-1017 vision",
        "glm-flash-vision": "z-ai/glm-5.3-flash vision",
        "spacy": "spaCy en_core_web_sm 3.8.0",
        "gliner-edge": "GLiNER PII Edge v1.0 UINT8",
        "gliner-small": "GLiNER PII Small v1.0 UINT8",
        "openmed": "OpenMed SuperClinical Small INT8",
    }
    return labels.get(name, "Unspecified model")


def text_context(report: dict[str, object], mode: str) -> str:
    if report.get("offline_replay") is True:
        return (
            "Verifier v3 replay: raw metrics/timing copied from historical requests"
            if mode == "raw_ner"
            else "Verifier v3 replay plus local fallback; time is local rescoring"
        )
    if report.get("verifier_version") is not None:
        return "Verifier v3 local host regression; no container limits"
    if report.get("remote_models_enabled") is True:
        return (
            "Historical live hosted detection; includes rejected responses"
            if mode == "raw_ner"
            else "Historical local-verifier rescoring; time is not endpoint latency"
        )
    return "Historical constrained local evaluation; timing excludes loading"


def verifier_version(report: dict[str, object]) -> str | None:
    version = report.get("verifier_version")
    return (
        version
        if isinstance(version, str) and re.fullmatch(r"verifier-v[0-9]+", version)
        else None
    )


def platform_label(report: dict[str, object]) -> str:
    value = report.get("platform")
    if isinstance(value, str):
        if value.startswith("Linux"):
            return "Linux container"
        if value.startswith("macOS"):
            return "macOS host"
    if (
        report.get("remote_models_enabled") is True
        or report.get("offline_replay") is True
    ):
        return (
            "Hosted client on macOS"
            if report.get("remote_models_enabled")
            else "macOS host"
        )
    return "Not recorded"


def model_label(value: object) -> str:
    labels = {
        "en_core_web_sm": "spaCy en_core_web_sm 3.8.0",
        ".models/gliner-pii-edge-v1.0": "GLiNER PII Edge v1.0 UINT8",
        ".models/gliner-pii-small-v1.0": "GLiNER PII Small v1.0 UINT8",
        ".models/OpenMed-PII-SuperClinical-Small-44M-v1-onnx-android": (
            "OpenMed SuperClinical Small INT8"
        ),
        "deepseek/deepseek-v4.1-flash-1017": "deepseek/deepseek-v4.1-flash-1017",
        "deepseek/deepseek-v4-pro": "deepseek/deepseek-v4-pro",
        "z-ai/glm-5.3-flash": "z-ai/glm-5.3-flash",
    }
    return (
        labels.get(value, "Unspecified model")
        if isinstance(value, str)
        else "Unspecified model"
    )


def corpus_digest(report: dict[str, object]) -> str | None:
    value = report.get("corpus_sha256")
    return (
        value
        if isinstance(value, str) and re.fullmatch(SHA256_PATTERN, value)
        else None
    )
