"""Reject source carriers that a rewrite could silently discard or collapse."""

from pathlib import Path
from zipfile import ZipFile

from redactor.formats.xlsx import shared_strings
from redactor.schemas.native import NativeDocument
from redactor.utils.constants import XLSX_WORKSHEET_PREFIX
from redactor.utils.errors import ERROR_COVERAGE
from redactor.verification.worksheet import check_worksheet_cells
from redactor.verification.xml import read_verified_xml
from redactor.verification.xml_vocabulary import check_xml_vocabulary


def check_xlsx_source_surfaces(path: Path, document: NativeDocument) -> None:
    covered = {location for record in document.records for location in record.locations}
    with ZipFile(path) as archive:
        strings = shared_strings(archive)
        for part in archive.namelist():
            root = read_verified_xml(archive.read(part))
            check_xml_vocabulary(root, part)
            if any(node.tail and node.tail.strip() for node in root.iter()):
                raise ValueError(ERROR_COVERAGE)
            if part.startswith(XLSX_WORKSHEET_PREFIX):
                check_worksheet_cells(root, part, covered, strings=strings)
