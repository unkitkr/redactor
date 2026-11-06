"""Initial native-parser checks; content coverage is established during analysis."""

import warnings
from pathlib import Path

from PIL import Image, UnidentifiedImageError

from redactor.schemas.configuration import ResourceSettings
from redactor.utils.errors import (
    ERROR_ENCRYPTED_INPUT,
    ERROR_RESOURCE_LIMIT,
    ERROR_STRUCTURE,
)


def inspect_image(path: Path, resources: ResourceSettings) -> int:
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error")
            with Image.open(path) as image:
                _check_pixels(image.width, image.height, resources)
                image.verify()
            with Image.open(path) as image:
                frames = 0
                while True:
                    _check_pixels(image.width, image.height, resources)
                    image.load()
                    frames += 1
                    try:
                        image.seek(frames)
                    except EOFError:
                        break
                return frames
    except (UnidentifiedImageError, OSError, SyntaxError, Warning):
        raise ValueError(ERROR_STRUCTURE) from None
    except Image.DecompressionBombError:
        raise ValueError(ERROR_RESOURCE_LIMIT) from None


def inspect_pdf(path: Path) -> int:
    import pymupdf

    show_errors = pymupdf.TOOLS.mupdf_display_errors()
    show_warnings = pymupdf.TOOLS.mupdf_display_warnings()
    try:
        # Native diagnostics may contain document data. The worker reports codes.
        pymupdf.TOOLS.mupdf_display_errors(False)
        pymupdf.TOOLS.mupdf_display_warnings(False)
        with pymupdf.open(path) as document:
            if document.needs_pass:
                raise ValueError(ERROR_ENCRYPTED_INPUT)
            if not document.is_pdf or document.is_repaired or document.page_count == 0:
                raise ValueError(ERROR_STRUCTURE)
            for page in document:
                if page.rect.is_empty or page.rect.is_infinite:
                    raise ValueError(ERROR_STRUCTURE)
            return int(document.page_count)
    except (pymupdf.FileDataError, RuntimeError):
        raise ValueError(ERROR_STRUCTURE) from None
    finally:
        pymupdf.TOOLS.mupdf_display_errors(show_errors)
        pymupdf.TOOLS.mupdf_display_warnings(show_warnings)


def inspect_dicom(path: Path, resources: ResourceSettings) -> int:
    import pydicom
    from pydicom.errors import InvalidDicomError

    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error")
            dataset = pydicom.dcmread(path, force=False)
            metadata = dataset.file_meta
            if (
                not metadata.TransferSyntaxUID
                or dataset.SOPClassUID != metadata.MediaStorageSOPClassUID
                or dataset.SOPInstanceUID != metadata.MediaStorageSOPInstanceUID
            ):
                raise ValueError(ERROR_STRUCTURE)
            # Force deferred element conversion before accepting the parse.
            for element in dataset.iterall():
                _ = element.value
            if hasattr(dataset, "Rows") and hasattr(dataset, "Columns"):
                _check_pixels(int(dataset.Columns), int(dataset.Rows), resources)
            frames = int(getattr(dataset, "NumberOfFrames", 1))
            if frames < 1:
                raise ValueError(ERROR_STRUCTURE)
            return frames
    except (InvalidDicomError, AttributeError, EOFError, TypeError, Warning):
        raise ValueError(ERROR_STRUCTURE) from None


def _check_pixels(width: int, height: int, resources: ResourceSettings) -> None:
    if width <= 0 or height <= 0:
        raise ValueError(ERROR_STRUCTURE)
    if width * height > resources.max_image_pixels:
        raise ValueError(ERROR_RESOURCE_LIMIT)
