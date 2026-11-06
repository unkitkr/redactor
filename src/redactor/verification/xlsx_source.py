"""Reject source carriers that a rewrite could silently discard or collapse."""

import re
from pathlib import Path
from zipfile import ZipFile

from redactor.formats.office_references import (
    relationship_labels,
    rewrite_relationship_labels,
)
from redactor.formats.xlsx import shared_strings
from redactor.schemas.native import NativeDocument
from redactor.utils.constants import XLSX_VML_PATTERN, XLSX_WORKSHEET_PREFIX
from redactor.utils.errors import ERROR_COVERAGE
from redactor.verification.vml import check_comment_shapes
from redactor.verification.worksheet import check_worksheet_cells
from redactor.verification.xml import read_verified_xml
from redactor.verification.xml_vocabulary import check_xml_vocabulary


def check_xlsx_source_surfaces(path: Path, document: NativeDocument) -> None:
    covered = {location for record in document.records for location in record.locations}
    with ZipFile(path) as archive:
        strings = shared_strings(archive)
        labels = relationship_labels(archive)
        for part in archive.namelist():
            root = read_verified_xml(archive.read(part))
            if re.fullmatch(XLSX_VML_PATTERN, part):
                check_comment_shapes(root)
                continue
            rewrite_relationship_labels(root, part, labels)
            check_xml_vocabulary(root, part)
            if any(node.tail and node.tail.strip() for node in root.iter()):
                raise ValueError(ERROR_COVERAGE)
            if part.startswith(XLSX_WORKSHEET_PREFIX):
                check_worksheet_cells(root, part, covered, strings=strings)
