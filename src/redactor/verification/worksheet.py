"""Account for every worksheet cell and reject ambiguous coordinate layouts."""

import re
from xml.etree.ElementTree import Element

from redactor.formats.tabular_fields import column_policies
from redactor.schemas.redaction import ColumnPolicy
from redactor.utils.constants import FIELD_TEXT, XLSX_NAMESPACE
from redactor.utils.errors import ERROR_COVERAGE, ERROR_STRUCTURE


def check_worksheet_cells(
    root: Element,
    part: str,
    covered: set[tuple[str, ...]],
    *,
    strings: tuple[str, ...] | None = None,
) -> None:
    sheets = root.findall(f"{{{XLSX_NAMESPACE}}}sheetData")
    if len(sheets) != 1:
        raise ValueError(ERROR_COVERAGE)
    rows = tuple(sheets[0])
    row_numbers: set[int] = set()
    seen: set[str] = set()
    cells: set[Element] = set()
    for index, row in enumerate(rows):
        if row.tag != f"{{{XLSX_NAMESPACE}}}row":
            raise ValueError(ERROR_COVERAGE)
        number = row.attrib.get("r", "")
        if re.fullmatch(r"[1-9][0-9]*", number) is None or int(number) in row_numbers:
            raise ValueError(ERROR_STRUCTURE)
        row_numbers.add(int(number))
        for cell in row:
            coordinate = cell.attrib.get("r", "")
            if (
                cell.tag != f"{{{XLSX_NAMESPACE}}}c"
                or re.fullmatch(rf"[A-Z]+{number}", coordinate) is None
                or coordinate in seen
            ):
                raise ValueError(ERROR_STRUCTURE)
            seen.add(coordinate)
            cells.add(cell)
            value = _cell_text(cell, strings)
            if (part, coordinate) not in covered:
                policy: ColumnPolicy = column_policies((value,))[0]
                if index != 0 or policy.kind == FIELD_TEXT:
                    raise ValueError(ERROR_COVERAGE)
    if cells != set(root.iter(f"{{{XLSX_NAMESPACE}}}c")):
        raise ValueError(ERROR_COVERAGE)


def _cell_text(cell: Element, strings: tuple[str, ...] | None) -> str:
    """Each supported cell has one value carrier; ignored alternatives are unsafe."""
    if cell.text and cell.text.strip():
        raise ValueError(ERROR_COVERAGE)
    kind = cell.attrib.get("t", "n")
    if not len(cell):
        return ""
    if kind == "inlineStr":
        expected = (f"{{{XLSX_NAMESPACE}}}is", f"{{{XLSX_NAMESPACE}}}t")
        if len(cell) != 1 or cell[0].tag != expected[0]:
            raise ValueError(ERROR_COVERAGE)
        inline = cell[0]
        if inline.text and inline.text.strip():
            raise ValueError(ERROR_COVERAGE)
        if not len(inline):
            return ""
        if len(inline) != 1 or inline[0].tag != expected[1] or len(inline[0]):
            raise ValueError(ERROR_COVERAGE)
        return inline[0].text or ""
    if len(cell) > 1:
        raise ValueError(ERROR_COVERAGE)
    if cell[0].tag != f"{{{XLSX_NAMESPACE}}}v" or len(cell[0]):
        raise ValueError(ERROR_COVERAGE)
    value = cell[0].text or ""
    if kind == "s":
        if strings is None or not value.isascii() or not value.isdigit():
            raise ValueError(ERROR_COVERAGE)
        index = int(value)
        if index >= len(strings):
            raise ValueError(ERROR_STRUCTURE)
        return strings[index]
    return value
