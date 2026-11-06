"""Dispatch bounded native-format records without converting their container."""

from pathlib import Path

from redactor.formats.hl7 import read_hl7
from redactor.formats.hl7_encoding import write_hl7
from redactor.formats.text import read_text, write_text
from redactor.formats.xlsx import read_xlsx, write_xlsx
from redactor.schemas.configuration import ResourceSettings
from redactor.schemas.formats import FileInspection
from redactor.schemas.native import NativeDocument
from redactor.utils.constants import FORMAT_HL7, FORMAT_TEXT, FORMAT_XLSX, TEXT_ENCODING
from redactor.utils.errors import ERROR_FORMAT_UNSUPPORTED, ERROR_RESOURCE_LIMIT


def read_native(
    path: Path, inspection: FileInspection, resources: ResourceSettings
) -> NativeDocument:
    if path.stat().st_size > resources.max_native_file_bytes:
        raise ValueError(ERROR_RESOURCE_LIMIT)
    if inspection.file_type == FORMAT_XLSX:
        return read_xlsx(path, resources)
    if inspection.file_type == FORMAT_HL7:
        return read_hl7(path, inspection.encoding or TEXT_ENCODING)
    if inspection.file_type == FORMAT_TEXT:
        return read_text(path, inspection.encoding or TEXT_ENCODING)
    raise ValueError(ERROR_FORMAT_UNSUPPORTED)


def write_native(
    original: Path,
    output: Path,
    inspection: FileInspection,
    replacements: dict[tuple[str, ...], str],
) -> None:
    if inspection.file_type == FORMAT_XLSX:
        write_xlsx(original, output, replacements)
        return
    if inspection.file_type == FORMAT_HL7:
        write_hl7(original, output, replacements, inspection.encoding or TEXT_ENCODING)
        return
    if inspection.file_type == FORMAT_TEXT:
        write_text(original, output, replacements, inspection.encoding or TEXT_ENCODING)
        return
    raise ValueError(ERROR_FORMAT_UNSUPPORTED)
