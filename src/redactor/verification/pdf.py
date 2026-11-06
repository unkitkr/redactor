"""Validate PDF geometry and non-text surfaces independently of text policy."""

from pathlib import Path
from typing import Any

import pymupdf

from redactor.formats.pdf import pdf_csv_attachment, pdf_images, validate_pdf_surfaces
from redactor.formats.tabular_fields import column_policies
from redactor.schemas.native import NativeDocument
from redactor.utils.constants import FIELD_TEXT, TEXT_ENCODING
from redactor.utils.errors import ERROR_COVERAGE, ERROR_STRUCTURE


def _drawings(page: pymupdf.Page) -> list[dict[str, Any]]:
    return [
        {key: value for key, value in item.items() if key != "seqno"}
        for item in page.get_drawings()
    ]


def check_pdf_structure(
    original: Path, output: Path, original_document: NativeDocument
) -> None:
    with pymupdf.open(original) as before, pymupdf.open(output) as after:
        validate_pdf_surfaces(before)
        validate_pdf_surfaces(after)
        if len(before) != len(after) or before.embfile_count() != after.embfile_count():
            raise ValueError(ERROR_STRUCTURE)
        for number in range(before.embfile_count()):
            source_suffix = Path(
                before.embfile_info(number)["filename"]
            ).suffix.casefold()
            saved_suffix = Path(
                after.embfile_info(number)["filename"]
            ).suffix.casefold()
            if source_suffix == ".csv":
                if saved_suffix != source_suffix:
                    raise ValueError(ERROR_STRUCTURE)
                source_rows, source_delimiter = pdf_csv_attachment(
                    before.embfile_get(number).decode(TEXT_ENCODING)
                )
                saved_rows, saved_delimiter = pdf_csv_attachment(
                    after.embfile_get(number).decode(TEXT_ENCODING)
                )
                if source_delimiter != saved_delimiter or len(source_rows) != len(
                    saved_rows
                ):
                    raise ValueError(ERROR_STRUCTURE)
                for policy in column_policies(tuple(source_rows[0])):
                    if (
                        policy.kind != FIELD_TEXT
                        and source_rows[0][policy.index] != saved_rows[0][policy.index]
                    ):
                        raise ValueError(ERROR_STRUCTURE)
        if len(pdf_images(after)) != len(original_document.images):
            raise ValueError(ERROR_COVERAGE)
        original_outline = [
            (item[0], item[2], item[3].get("to"), item[3].get("zoom"))
            for item in before.get_toc(simple=False)
        ]
        saved_outline = [
            (item[0], item[2], item[3].get("to"), item[3].get("zoom"))
            for item in after.get_toc(simple=False)
        ]
        if original_outline != saved_outline:
            raise ValueError(ERROR_STRUCTURE)
        for source, saved in zip(before, after, strict=True):
            if (
                source.rect != saved.rect
                or source.rotation != saved.rotation
                or _drawings(source) != _drawings(saved)
            ):
                raise ValueError(ERROR_STRUCTURE)
            source_images = [
                (
                    tuple(item["bbox"]),
                    tuple(item["transform"]),
                    item["width"],
                    item["height"],
                )
                for item in source.get_image_info()
            ]
            saved_images = [
                (
                    tuple(item["bbox"]),
                    tuple(item["transform"]),
                    item["width"],
                    item["height"],
                )
                for item in saved.get_image_info()
            ]
            if source_images != saved_images:
                raise ValueError(ERROR_STRUCTURE)
            source_annotations = [
                (annotation.type, tuple(annotation.rect), annotation.colors)
                for annotation in source.annots() or ()
            ]
            saved_annotations = [
                (annotation.type, tuple(annotation.rect), annotation.colors)
                for annotation in saved.annots() or ()
            ]
            if source_annotations != saved_annotations:
                raise ValueError(ERROR_STRUCTURE)
            source_widgets = [
                (widget.field_type, tuple(widget.rect), widget.field_flags)
                for widget in source.widgets() or ()
            ]
            saved_widgets = [
                (widget.field_type, tuple(widget.rect), widget.field_flags)
                for widget in saved.widgets() or ()
            ]
            if source_widgets != saved_widgets:
                raise ValueError(ERROR_STRUCTURE)
