"""Compare workbook structure after removing only explicitly assessed values."""

from itertools import zip_longest
from pathlib import Path
from xml.etree.ElementTree import Element
from zipfile import ZipFile

from redactor.formats.office_references import (
    relationship_labels,
    rewrite_relationship_labels,
)
from redactor.formats.xlsx import shared_strings
from redactor.schemas.native import NativeDocument
from redactor.utils.constants import (
    OFFICE_XML_TEXT_MODE,
    XLSX_NAMESPACE,
    XLSX_SHARED_STRINGS,
    XLSX_WORKSHEET_PREFIX,
)
from redactor.utils.errors import ERROR_CLINICAL_CHANGED
from redactor.verification.xml import read_verified_xml


def check_xlsx_preservation(
    source: Path, saved: Path, document: NativeDocument
) -> None:
    covered = {location for record in document.records for location in record.locations}
    with ZipFile(source) as original, ZipFile(saved) as output:
        if original.namelist() != output.namelist():
            raise ValueError(ERROR_CLINICAL_CHANGED)
        strings = shared_strings(original)
        source_labels, saved_labels = (
            relationship_labels(original),
            relationship_labels(output),
        )
        for part in original.namelist():
            if part == XLSX_SHARED_STRINGS:
                # Saved cells carry their strings inline; the saved-surface check
                # requires this removed pool to be empty.
                continue
            before = read_verified_xml(original.read(part))
            after = read_verified_xml(output.read(part))
            rewrite_relationship_labels(before, part, source_labels)
            rewrite_relationship_labels(after, part, saved_labels)
            _neutralize_assessed_values(before, part, covered, strings)
            _neutralize_assessed_values(after, part, covered, ())
            for left, right in zip_longest(before.iter(), after.iter()):
                if (
                    left is None
                    or right is None
                    or left.tag != right.tag
                    or left.attrib != right.attrib
                    or (left.text or "").strip() != (right.text or "").strip()
                    or len(left) != len(right)
                ):
                    raise ValueError(ERROR_CLINICAL_CHANGED)


def _neutralize_assessed_values(
    root: Element,
    part: str,
    covered: set[tuple[str, ...]],
    strings: tuple[str, ...],
) -> None:
    if part.startswith(XLSX_WORKSHEET_PREFIX):
        for cell in root.iter(f"{{{XLSX_NAMESPACE}}}c"):
            value = ""
            if (part, cell.attrib["r"]) not in covered:
                # Known structural headers are not edits and must remain equal.
                if cell.attrib.get("t") == "s":
                    value = strings[int(cell.findtext(f"{{{XLSX_NAMESPACE}}}v", "-1"))]
                elif cell.attrib.get("t") == "inlineStr":
                    value = "".join(
                        node.text or "" for node in cell.iter(f"{{{XLSX_NAMESPACE}}}t")
                    )
                else:
                    value = cell.findtext(f"{{{XLSX_NAMESPACE}}}v", "")
            for child in tuple(cell):
                cell.remove(child)
            cell.attrib.pop("t", None)
            cell.text = value
        return
    for index, node in enumerate(root.iter()):
        if (part, str(index), OFFICE_XML_TEXT_MODE) in covered:
            for text in node.iter(f"{{{XLSX_NAMESPACE}}}t"):
                text.text = ""
        if (part, str(index)) in covered:
            node.text = ""
        for attribute in node.attrib:
            if (part, str(index), attribute) in covered:
                node.attrib[attribute] = ""
