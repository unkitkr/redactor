"""Inspect, read and save native content using ordinary function calls."""

import hashlib
from pathlib import Path

from redactor.formats.csv import (
    encode_csv_header,
    encode_csv_record,
    iter_csv_records,
)
from redactor.formats.embedded_images import rewrite_embedded_images
from redactor.formats.images import encode_image_frames, mask_image, read_image_frames
from redactor.formats.inspection import inspect_file
from redactor.formats.native import read_native, write_native
from redactor.formats.tabular_fields import column_policies
from redactor.policy.text import apply_text_edits
from redactor.schemas.configuration import PipelineSettings
from redactor.schemas.native import NativeDocument, NativeRecord
from redactor.schemas.simple import ExtractedFile, RedactedFile
from redactor.utils.constants import IMAGE_FORMATS, SIMPLE_MAX_RECORDS
from redactor.utils.errors import (
    ERROR_COVERAGE,
    ERROR_INPUT_CHANGED,
    ERROR_RESOURCE_LIMIT,
)


def file_digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def extract_file(path: Path, settings: PipelineSettings) -> ExtractedFile:
    """Read all surfaces, rejecting large inputs rather than sampling them."""
    if path.stat().st_size > settings.resources.max_native_file_bytes:
        raise ValueError(ERROR_RESOURCE_LIMIT)
    digest = file_digest(path)
    inspection = inspect_file(path, settings.resources)
    if inspection.reason is not None:
        raise ValueError(inspection.reason)
    if inspection.file_type in IMAGE_FORMATS:
        document = NativeDocument(records=())
    elif inspection.csv_layout is not None:
        layout = inspection.csv_layout
        policies = column_policies(layout.columns)
        records: list[NativeRecord] = []
        for row in iter_csv_records(path, layout, settings.resources.max_record_bytes):
            if len(records) >= SIMPLE_MAX_RECORDS:
                raise ValueError(ERROR_RESOURCE_LIMIT)
            records.append(
                NativeRecord(
                    values=row.values,
                    policies=policies,
                    locations=tuple(
                        (str(row.number), str(column.index)) for column in policies
                    ),
                )
            )
        document = NativeDocument(records=tuple(records))
    else:
        document = read_native(path, inspection, settings.resources)
    if len(document.records) > SIMPLE_MAX_RECORDS:
        raise ValueError(ERROR_RESOURCE_LIMIT)
    if file_digest(path) != digest:
        raise ValueError(ERROR_INPUT_CHANGED)
    return ExtractedFile(
        path=path,
        sha256=digest,
        inspection=inspection,
        document=document,
    )


def save_file(plan: RedactedFile, output: Path, settings: PipelineSettings) -> None:
    source = plan.analysis.source
    if source.inspection.file_type in IMAGE_FORMATS:
        frames = read_image_frames(source.path, settings.resources)
        if len(frames) != len(plan.analysis.frames):
            raise ValueError(ERROR_COVERAGE)
        masked = tuple(
            mask_image(frame, evidence.masks)
            for frame, evidence in zip(frames, plan.analysis.frames, strict=True)
        )
        output.write_bytes(
            encode_image_frames(masked, source.inspection.file_type.upper())
        )
        return
    layout = source.inspection.csv_layout
    if layout is not None:
        with output.open("wb") as stream:
            stream.write(encode_csv_header(layout))
            for record, edits in zip(source.document.records, plan.edits, strict=True):
                values = tuple(
                    apply_text_edits(value, changes)
                    for value, changes in zip(record.values, edits, strict=True)
                )
                stream.write(encode_csv_record(values, layout))
        return
    replacements = {
        location: apply_text_edits(value, changes)
        for record, edits in zip(source.document.records, plan.edits, strict=True)
        for location, value, changes in zip(
            record.locations, record.values, edits, strict=True
        )
        if changes
    }
    images = rewrite_embedded_images(
        source.document.images, plan.analysis.images, settings
    )
    write_native(
        source.path, output, source.inspection, replacements, settings.resources, images
    )
