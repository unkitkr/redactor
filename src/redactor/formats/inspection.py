"""Detect content before extensions and reject invalid or oversized containers."""

import codecs
from pathlib import Path

from redactor.formats.archives import inspect_office_archive
from redactor.formats.csv import inspect_csv
from redactor.formats.json import inspect_json
from redactor.formats.native_inspection import inspect_dicom, inspect_image, inspect_pdf
from redactor.schemas.configuration import ResourceSettings
from redactor.schemas.formats import FileFormat, FileInspection
from redactor.utils.constants import (
    DICOM_PREAMBLE_BYTES,
    DICOM_SIGNATURE,
    FORMAT_CSV,
    FORMAT_DICOM,
    FORMAT_HL7,
    FORMAT_JPEG,
    FORMAT_JSON,
    FORMAT_OLE,
    FORMAT_PDF,
    FORMAT_PNG,
    FORMAT_PROBE_BYTES,
    FORMAT_TEXT,
    FORMAT_TIFF,
    FORMAT_TSV,
    FORMAT_UNKNOWN,
    FORMAT_ZIP,
    HL7_SIGNATURE,
    JPEG_SIGNATURE,
    LEGACY_TEXT_ENCODING,
    OLE_SIGNATURE,
    PDF_SIGNATURE,
    PNG_SIGNATURE,
    TEXT_ALLOWED_CONTROLS,
    TEXT_ENCODING,
    TIFF_SIGNATURES,
    UTF8_BOM,
    UTF8_BOM_ENCODING,
    ZIP_SIGNATURE,
)
from redactor.utils.errors import (
    ERROR_FORMAT_UNSUPPORTED,
    ERROR_RESOURCE_LIMIT,
    ERROR_STRUCTURE,
    ERROR_TEXT_ENCODING,
    INSPECTION_REASON_CODES,
)


def inspect_file(path: Path, resources: ResourceSettings) -> FileInspection:
    with path.open("rb") as stream:
        probe = stream.read(FORMAT_PROBE_BYTES)
    file_type = identify_format(probe)
    try:
        if file_type == FORMAT_ZIP:
            actual_type = inspect_office_archive(path, resources)
            return FileInspection(file_type=actual_type)
        if file_type in (FORMAT_UNKNOWN, FORMAT_OLE):
            raise ValueError(ERROR_FORMAT_UNSUPPORTED)
        if file_type in (
            FORMAT_PDF,
            FORMAT_DICOM,
            FORMAT_JPEG,
            FORMAT_PNG,
            FORMAT_TIFF,
        ):
            if path.stat().st_size > resources.max_native_file_bytes:
                raise ValueError(ERROR_RESOURCE_LIMIT)
            if file_type == FORMAT_PDF:
                units = inspect_pdf(path)
            elif file_type == FORMAT_DICOM:
                units = inspect_dicom(path, resources)
            else:
                units = inspect_image(path, resources)
            return FileInspection(file_type=file_type, units=units)
        if file_type == FORMAT_JSON:
            actual_type, units = inspect_json(path, resources)
            return FileInspection(
                file_type=actual_type, units=units, encoding=TEXT_ENCODING
            )
        encoding = _text_encoding(probe)
        if file_type == FORMAT_HL7:
            _validate_text(path, encoding, resources)
            return FileInspection(file_type=file_type, encoding=encoding)
        # Delimiters in the first physical line nominate a table. A malformed
        # table must not silently fall through to a less strict text processor.
        first_line = probe.removeprefix(UTF8_BOM).splitlines()[0] if probe else b""
        if any(separator in first_line for separator in (b",", b"\t", b";")):
            layout = inspect_csv(path, resources.max_record_bytes)
            actual_type = FORMAT_TSV if layout.delimiter == "\t" else FORMAT_CSV
            return FileInspection(
                file_type=actual_type, csv_layout=layout, encoding=encoding
            )
        _validate_text(path, encoding, resources)
        return FileInspection(file_type=FORMAT_TEXT, encoding=encoding)
    except ValueError as error:
        reason = (
            str(error) if str(error) in INSPECTION_REASON_CODES else ERROR_STRUCTURE
        )
        return FileInspection(file_type=file_type, reason=reason)


def identify_format(probe: bytes) -> FileFormat:
    if probe.startswith(ZIP_SIGNATURE):
        return FORMAT_ZIP
    if probe.startswith(OLE_SIGNATURE):
        return FORMAT_OLE
    if probe.startswith(PDF_SIGNATURE):
        return FORMAT_PDF
    if (
        probe[DICOM_PREAMBLE_BYTES : DICOM_PREAMBLE_BYTES + len(DICOM_SIGNATURE)]
        == DICOM_SIGNATURE
    ):
        return FORMAT_DICOM
    if probe.startswith(JPEG_SIGNATURE):
        return FORMAT_JPEG
    if probe.startswith(PNG_SIGNATURE):
        return FORMAT_PNG
    if probe.startswith(TIFF_SIGNATURES):
        return FORMAT_TIFF
    text_probe = probe.removeprefix(UTF8_BOM).lstrip()
    if text_probe.startswith((b"{", b"[")):
        return FORMAT_JSON
    if text_probe.startswith(HL7_SIGNATURE) and len(text_probe) >= 8:
        return FORMAT_HL7
    if not probe or any(
        byte < 32 and byte not in TEXT_ALLOWED_CONTROLS for byte in probe
    ):
        return FORMAT_UNKNOWN
    return FORMAT_TEXT


def _text_encoding(probe: bytes) -> str:
    if probe.startswith(UTF8_BOM):
        return UTF8_BOM_ENCODING
    try:
        codecs.getincrementaldecoder(TEXT_ENCODING)().decode(probe, final=False)
        return TEXT_ENCODING
    except UnicodeDecodeError:
        try:
            probe.decode(LEGACY_TEXT_ENCODING)
            return LEGACY_TEXT_ENCODING
        except UnicodeDecodeError:
            raise ValueError(ERROR_TEXT_ENCODING) from None


def _validate_text(path: Path, encoding: str, resources: ResourceSettings) -> None:
    decoder = codecs.getincrementaldecoder(encoding)()
    try:
        with path.open("rb") as stream:
            while chunk := stream.read(resources.chunk_bytes):
                if any(
                    byte < 32 and byte not in TEXT_ALLOWED_CONTROLS for byte in chunk
                ):
                    raise ValueError(ERROR_STRUCTURE)
                decoder.decode(chunk)
        decoder.decode(b"", final=True)
    except UnicodeDecodeError:
        raise ValueError(ERROR_TEXT_ENCODING) from None
