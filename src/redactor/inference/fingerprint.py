"""Bind a run to installed code and model bytes without loading a model."""

import hashlib
import platform
import shutil
from importlib.metadata import PackageNotFoundError, distribution, version
from pathlib import Path

from redactor.schemas.configuration import LocalSettings
from redactor.utils.constants import (
    HASH_CHUNK_BYTES,
    OCR_PPOCR,
    OCR_PPOCR_DIRECTORY,
    OCR_TESSDATA_DIRECTORY,
    OCR_TESSERACT,
    RUNTIME_IGNORED_SUFFIXES,
    RUNTIME_MISSING_ARTIFACT,
    RUNTIME_PACKAGES,
    RUNTIME_SOURCE_SUFFIXES,
)


def runtime_fingerprint(settings: LocalSettings) -> str:
    """Missing assets are explicit, so installing them also changes run identity.

    Runtime files must remain read-only during execution. A container image and
    read-only model mounts provide that boundary; this detects changes at startup.
    """
    values = {
        "python": platform.python_version(),
        "implementation": platform.python_implementation(),
        "system": platform.system(),
        "machine": platform.machine(),
        "source": directory_fingerprint(
            Path(__file__).resolve().parents[1], suffixes=RUNTIME_SOURCE_SUFFIXES
        ),
        "spacy_model": package_fingerprint(settings.spacy_model),
    }
    for package in RUNTIME_PACKAGES:
        try:
            values[package] = version(package)
        except PackageNotFoundError:
            values[package] = RUNTIME_MISSING_ARTIFACT
    if settings.ner_directory is not None:
        values["ner"] = directory_fingerprint(settings.ner_directory)
    ocr_directory = settings.ocr_directory or settings.model_directory / (
        OCR_PPOCR_DIRECTORY if settings.ocr == OCR_PPOCR else OCR_TESSDATA_DIRECTORY
    )
    values["ocr"] = directory_fingerprint(ocr_directory)
    executable = shutil.which(OCR_TESSERACT)
    values["tesseract"] = (
        file_fingerprint(Path(executable)) if executable else RUNTIME_MISSING_ARTIFACT
    )
    return _combine(values)


def package_fingerprint(name: str) -> str:
    """Hash actual packaged model files, including weights, not just its version."""
    try:
        package = distribution(name)
    except PackageNotFoundError:
        return RUNTIME_MISSING_ARTIFACT
    return _combine(
        {
            str(path): file_fingerprint(Path(str(package.locate_file(path))))
            for path in package.files or ()
            if path.suffix not in RUNTIME_IGNORED_SUFFIXES
        }
    )


def directory_fingerprint(path: Path, *, suffixes: tuple[str, ...] = ()) -> str:
    if not path.is_dir():
        return RUNTIME_MISSING_ARTIFACT
    return _combine(
        {
            file.relative_to(path).as_posix(): file_fingerprint(file)
            for file in path.rglob("*")
            if file.is_file()
            and file.suffix not in RUNTIME_IGNORED_SUFFIXES
            and (not suffixes or file.suffix in suffixes)
        }
    )


def file_fingerprint(path: Path) -> str:
    digest = hashlib.sha256()
    if not path.is_file():
        return RUNTIME_MISSING_ARTIFACT
    with path.open("rb") as stream:
        while block := stream.read(HASH_CHUNK_BYTES):
            digest.update(block)
    return digest.hexdigest()


def _combine(values: dict[str, str]) -> str:
    digest = hashlib.sha256()
    for name, value in sorted(values.items()):
        for part in (name, value):
            encoded = part.encode()
            digest.update(len(encoded).to_bytes(8, "big"))
            digest.update(encoded)
    return digest.hexdigest()
