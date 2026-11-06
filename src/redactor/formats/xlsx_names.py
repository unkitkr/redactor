"""Expose workbook labels and preserve the targets of bounded named ranges."""

import re
from xml.etree.ElementTree import Element

from openpyxl.formula.tokenizer import Token, Tokenizer, TokenizerError
from openpyxl.utils.cell import range_boundaries

from redactor.schemas.native import NativeRecord
from redactor.schemas.redaction import ColumnPolicy
from redactor.utils.constants import (
    FIELD_IDENTIFIER,
    FIELD_TEXT,
    XLSX_BUILTIN_NAMES,
    XLSX_MAX_COLUMNS,
    XLSX_MAX_ROWS,
    XLSX_MAX_SHEET_NAME,
    XLSX_NAME_NAMESPACE,
    XLSX_NAME_PREFIX,
    XLSX_NAMESPACE,
    XLSX_RANGE_PATTERN,
    XLSX_WORKBOOK,
)
from redactor.utils.errors import ERROR_COVERAGE, ERROR_STRUCTURE


def workbook_names(root: Element) -> tuple[str, ...]:
    sheets = root.findall(f"{{{XLSX_NAMESPACE}}}sheets/{{{XLSX_NAMESPACE}}}sheet")
    names = tuple(sheet.attrib.get("name", "") for sheet in sheets)
    if (
        not names
        or len({name.casefold() for name in names}) != len(names)
        or any(
            not name
            or len(name) > XLSX_MAX_SHEET_NAME
            or re.search(r"[\\/*?:\[\]]", name)
            for name in names
        )
        or not any(
            sheet.attrib.get("state", "visible") == "visible" for sheet in sheets
        )
    ):
        raise ValueError(ERROR_STRUCTURE)
    return names


def workbook_label_records(root: Element) -> tuple[NativeRecord, ...]:
    names = workbook_names(root)
    records = []
    defined_names: set[tuple[str, str]] = set()
    for index, node in enumerate(root.iter()):
        attributes: tuple[str, ...]
        if node.attrib.get("date1904") in ("1", "true"):
            raise ValueError(ERROR_COVERAGE)
        if node.tag == f"{{{XLSX_NAMESPACE}}}sheet":
            attributes = ("name",)
        elif node.tag == f"{{{XLSX_NAMESPACE}}}definedName":
            name = node.attrib.get("name", "")
            scope = node.attrib.get("localSheetId", "")
            if re.fullmatch(r"[^\W\d][\w.]*", name) is None or (
                scope
                and (
                    not scope.isascii()
                    or not scope.isdigit()
                    or int(scope) >= len(names)
                )
            ):
                raise ValueError(ERROR_STRUCTURE)
            scope = str(int(scope)) if scope else ""
            if (scope, name.casefold()) in defined_names:
                raise ValueError(ERROR_STRUCTURE)
            if name.startswith("_xlnm.") and name not in XLSX_BUILTIN_NAMES:
                raise ValueError(ERROR_COVERAGE)
            defined_names.add((scope, name.casefold()))
            rewrite_range_targets(node.text or "", names, {})
            attributes = tuple(
                attribute
                for attribute in ("name", "comment", "description")
                if attribute in node.attrib
            )
        else:
            continue
        for attribute in attributes:
            identifier = node.tag.endswith("}definedName") and attribute == "name"
            if identifier and node.attrib[attribute] in XLSX_BUILTIN_NAMES:
                continue
            records.append(
                NativeRecord(
                    values=(node.attrib[attribute],),
                    policies=(
                        ColumnPolicy(
                            index=0,
                            kind=FIELD_IDENTIFIER if identifier else FIELD_TEXT,
                            namespace=XLSX_NAME_NAMESPACE if identifier else "",
                            identifier_prefix=XLSX_NAME_PREFIX if identifier else "",
                        ),
                    ),
                    locations=((XLSX_WORKBOOK, str(index), attribute),),
                )
            )
    return tuple(records)


def rewrite_range_targets(
    value: str, names: tuple[str, ...], changes: dict[str, str]
) -> str:
    """Only explicit internal ranges are supported; expressions are not evaluated."""
    known = {name.casefold(): name for name in names}
    pieces = []
    cursor = 0
    expect_range = True
    try:
        tokens = Tokenizer("=" + value).items
        for token in tokens:
            if token.type == Token.WSPACE:
                match = re.match(r"\s+", value[cursor:])
                if match is None:
                    raise ValueError(ERROR_STRUCTURE)
                pieces.append(match[0])
                cursor += match.end()
                continue
            if not value.startswith(token.value, cursor):
                raise ValueError(ERROR_STRUCTURE)
            cursor += len(token.value)
            if (
                token.type == Token.OPERAND
                and token.subtype == Token.RANGE
                and expect_range
            ):
                sheet, separator, cells = token.value.rpartition("!")
                if (
                    not separator
                    or re.fullmatch(XLSX_RANGE_PATTERN, cells, re.IGNORECASE) is None
                ):
                    raise ValueError(ERROR_COVERAGE)
                if sheet.startswith("'") and sheet.endswith("'"):
                    sheet = sheet[1:-1].replace("''", "'")
                canonical = known.get(sheet.casefold())
                if canonical is None:
                    raise ValueError(ERROR_COVERAGE)
                left, top, right, bottom = range_boundaries(cells)
                if (
                    any(
                        position is not None and not 1 <= position <= limit
                        for position, limit in (
                            (left, XLSX_MAX_COLUMNS),
                            (right, XLSX_MAX_COLUMNS),
                            (top, XLSX_MAX_ROWS),
                            (bottom, XLSX_MAX_ROWS),
                        )
                    )
                    or (left is not None and right is not None and left > right)
                    or (top is not None and bottom is not None and top > bottom)
                ):
                    raise ValueError(ERROR_STRUCTURE)
                replacement = changes.get(canonical, canonical)
                pieces.append(
                    "'" + replacement.replace("'", "''") + "'!" + cells
                    if replacement != canonical
                    else token.value
                )
                expect_range = False
            elif token.type == Token.OP_IN and token.value == "," and not expect_range:
                pieces.append(token.value)
                expect_range = True
            else:
                raise ValueError(ERROR_COVERAGE)
    except (IndexError, KeyError, TokenizerError):
        raise ValueError(ERROR_STRUCTURE) from None
    if expect_range or cursor != len(value):
        raise ValueError(ERROR_STRUCTURE)
    return "".join(pieces)
