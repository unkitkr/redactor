"""Reject residual Office surfaces outside the supported cell and metadata model."""

import re
from pathlib import Path
from zipfile import ZipFile

from redactor.schemas.native import NativeDocument
from redactor.utils.constants import (
    OFFICE_PUBLIC_FONTS,
    OFFICE_STRUCTURAL_VALUES,
    XLSX_NAMESPACE,
    XLSX_SHARED_STRINGS,
    XLSX_STYLES,
    XLSX_WORKBOOK,
    XLSX_WORKSHEET_PREFIX,
)
from redactor.utils.errors import ERROR_COVERAGE, ERROR_RESIDUAL_PHI
from redactor.verification.worksheet import check_worksheet_cells
from redactor.verification.xml import read_verified_xml
from redactor.verification.xml_vocabulary import check_xml_vocabulary


def check_xlsx_surfaces(path: Path, document: NativeDocument) -> None:
    covered = {location for record in document.records for location in record.locations}
    with ZipFile(path) as archive:
        if archive.comment or any(
            entry.comment or entry.extra for entry in archive.infolist()
        ):
            raise ValueError(ERROR_COVERAGE)
        for part in archive.namelist():
            root = read_verified_xml(archive.read(part))
            check_xml_vocabulary(root, part)
            if any(node.tail and node.tail.strip() for node in root.iter()):
                raise ValueError(ERROR_COVERAGE)
            if part == XLSX_SHARED_STRINGS:
                if len(root) or (root.text and root.text.strip()):
                    raise ValueError(ERROR_RESIDUAL_PHI)
                continue
            if part.startswith(XLSX_WORKSHEET_PREFIX):
                check_worksheet_cells(root, part, covered)
                cells = set(root.iter(f"{{{XLSX_NAMESPACE}}}c"))
                cell_nodes = {node for cell in cells for node in cell.iter()}
                for node in root.iter():
                    if node not in cell_nodes and node.text and node.text.strip():
                        raise ValueError(ERROR_COVERAGE)
                    if node.tag.endswith("}f") or node.tag.endswith("}extLst"):
                        raise ValueError(ERROR_COVERAGE)
                    if (
                        node in cell_nodes
                        and node.text
                        and node.text.strip()
                        and not (node.tag.endswith("}v") or node.tag.endswith("}t"))
                    ):
                        raise ValueError(ERROR_COVERAGE)
                    for attribute, value in node.attrib.items():
                        if (
                            attribute == "{http://www.w3.org/XML/1998/namespace}space"
                            and value == "preserve"
                        ):
                            continue
                        if attribute in (
                            "r",
                            "ref",
                            "sqref",
                            "topLeftCell",
                        ) and re.fullmatch(r"[A-Z0-9: ]+", value):
                            continue
                        if attribute == "t" and value in (
                            "n",
                            "inlineStr",
                            "b",
                            "e",
                            "d",
                        ):
                            continue
                        if attribute in (
                            "s",
                            "ht",
                            "hidden",
                            "customHeight",
                            "customFormat",
                            "outlineLevel",
                            "collapsed",
                            "thickTop",
                            "thickBot",
                            "style",
                            "width",
                            "min",
                            "max",
                            "customWidth",
                            "bestFit",
                            "showGridLines",
                            "sheetViewId",
                            "workbookViewId",
                            "activeCellId",
                            "baseColWidth",
                            "defaultRowHeight",
                            "defaultColWidth",
                            "left",
                            "right",
                            "top",
                            "bottom",
                            "header",
                            "footer",
                            "count",
                        ) and re.fullmatch(r"[0-9]+(?:\.[0-9]+)?", value):
                            continue
                        if attribute == "activeCell" and re.fullmatch(
                            r"[A-Z]+[1-9][0-9]*", value
                        ):
                            continue
                        if attribute in (
                            "summaryRight",
                            "summaryBelow",
                            "showOutlineSymbols",
                            "fitToPage",
                            "autoPageBreaks",
                        ) and value in ("0", "1"):
                            continue
                        raise ValueError(ERROR_COVERAGE)
                continue
            for index, node in enumerate(root.iter()):
                if (
                    node.text
                    and node.text.strip()
                    and (part, str(index)) not in covered
                ):
                    raise ValueError(ERROR_COVERAGE)
                if node.tail and node.tail.strip():
                    raise ValueError(ERROR_COVERAGE)
                for attribute, value in node.attrib.items():
                    if (part, str(index), attribute) in covered:
                        continue
                    local = attribute.rsplit("}", 1)[-1]
                    if local == "TargetMode":
                        raise ValueError(ERROR_COVERAGE)
                    # Vocabulary validation checked the exact URI and its role.
                    if local in ("Type", "ContentType"):
                        continue
                    if part.endswith(".rels") and local == "Target":
                        if re.fullmatch(
                            r"/?(?:[A-Za-z_.]+/)*[A-Za-z_]+[0-9]*\.(?:xml|rels)", value
                        ):
                            continue
                        raise ValueError(ERROR_COVERAGE)
                    if part == "[Content_Types].xml":
                        if local in (
                            "Extension",
                            "ContentType",
                            "PartName",
                        ) and re.fullmatch(r"[a-zA-Z0-9/._+\-]+", value):
                            continue
                    if part == XLSX_STYLES and local == "formatCode":
                        if re.fullmatch(r"[ymdhsAMPM0#?.,%;:/\-\[\]@\\()$ ]+", value):
                            continue
                        raise ValueError(ERROR_COVERAGE)
                    if local == "typeface" or (
                        part == XLSX_STYLES
                        and node.tag.endswith("}name")
                        and local == "val"
                    ):
                        if value in OFFICE_PUBLIC_FONTS:
                            continue
                        raise ValueError(ERROR_COVERAGE)
                    if value in OFFICE_STRUCTURAL_VALUES or re.fullmatch(
                        r"[-+]?[0-9]+(?:\.[0-9]+)?|[0-9A-Fa-f]{6,8}|rId[0-9]+", value
                    ):
                        continue
                    if local == "script" and re.fullmatch(r"[A-Z][a-z]{3}", value):
                        continue
                    if local in (
                        "defaultTableStyle",
                        "defaultPivotStyle",
                    ) and re.fullmatch(
                        r"(?:Table|Pivot)Style(?:Light|Medium|Dark)[0-9]+", value
                    ):
                        continue
                    if local == "type" and value == "dcterms:W3CDTF":
                        continue
                    if part == XLSX_WORKBOOK and local == "name":
                        raise ValueError(ERROR_COVERAGE)
                    raise ValueError(ERROR_COVERAGE)
