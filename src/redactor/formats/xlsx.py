"""Read every worksheet and rewrite cell values without flattening the workbook."""

import re
from datetime import datetime, timedelta
from pathlib import Path
from xml.etree.ElementTree import Element, SubElement, tostring
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

from defusedxml.ElementTree import fromstring

from redactor.formats.tabular_fields import column_policies
from redactor.schemas.configuration import ResourceSettings
from redactor.schemas.native import NativeDocument, NativeRecord
from redactor.schemas.redaction import ColumnPolicy
from redactor.utils.constants import (
    FIELD_TEXT,
    XLSX_DATE_FORMAT_IDS,
    XLSX_EPOCH,
    XLSX_NAMESPACE,
    XLSX_SHARED_STRINGS,
    XLSX_STYLES,
    XLSX_WORKBOOK,
    XLSX_WORKSHEET_PREFIX,
    ZIP_FIXED_TIMESTAMP,
)
from redactor.utils.errors import ERROR_COVERAGE, ERROR_RESOURCE_LIMIT, ERROR_STRUCTURE


def read_xlsx(path: Path, resources: ResourceSettings) -> NativeDocument:
    records: list[NativeRecord] = []
    with ZipFile(path) as archive:
        if (
            sum(item.file_size for item in archive.infolist())
            > resources.max_archive_bytes
        ):
            raise ValueError(ERROR_RESOURCE_LIMIT)
        strings = shared_strings(archive)
        dates = date_styles(archive)
        for part in archive.namelist():
            if part.startswith(XLSX_WORKSHEET_PREFIX) and part.endswith(".xml"):
                root = fromstring(archive.read(part), forbid_dtd=True)
                rows = root.findall(f".//{{{XLSX_NAMESPACE}}}row")
                if not rows:
                    continue
                header = rows[0].findall(f"{{{XLSX_NAMESPACE}}}c")
                columns = tuple(cell_value(cell, strings, dates) for cell in header)
                positions = tuple(column_letters(cell.attrib["r"]) for cell in header)
                if not columns or len(set(positions)) != len(columns):
                    raise ValueError(ERROR_STRUCTURE)
                policies = column_policies(columns)
                for row in rows[1:]:
                    cells = {column_letters(cell.attrib["r"]): cell for cell in row}
                    if set(cells) - set(positions):
                        raise ValueError(ERROR_COVERAGE)
                    values = tuple(
                        cell_value(cells[position], strings, dates)
                        if position in cells
                        else ""
                        for position in positions
                    )
                    locations = tuple(
                        (part, position + row.attrib["r"]) for position in positions
                    )
                    records.append(
                        NativeRecord(
                            values=values, policies=policies, locations=locations
                        )
                    )
                # Unknown column labels can themselves contain identifying text.
                for cell, policy in zip(header, policies, strict=True):
                    if policy.kind == FIELD_TEXT:
                        records.append(
                            single_cell(
                                part, cell.attrib["r"], cell_value(cell, strings, dates)
                            )
                        )
                if root.findall(f".//{{{XLSX_NAMESPACE}}}f") or root.findall(
                    f".//{{{XLSX_NAMESPACE}}}hyperlink"
                ):
                    raise ValueError(ERROR_COVERAGE)
            elif part.startswith("docProps/") and part.endswith(".xml"):
                root = fromstring(archive.read(part), forbid_dtd=True)
                for index, element in enumerate(root.iter()):
                    if element.text and element.text.strip():
                        name = element.tag.rsplit("}", 1)[-1]
                        policy = column_policies((name,))[0]
                        records.append(
                            NativeRecord(
                                values=(element.text,),
                                policies=(policy,),
                                locations=((part, str(index)),),
                            )
                        )
            elif part == XLSX_WORKBOOK:
                root = fromstring(archive.read(part), forbid_dtd=True)
                for index, element in enumerate(root.iter()):
                    if element.tag == f"{{{XLSX_NAMESPACE}}}sheet":
                        records.append(
                            NativeRecord(
                                values=(element.attrib["name"],),
                                policies=(ColumnPolicy(index=0, kind=FIELD_TEXT),),
                                locations=((part, str(index), "name"),),
                            )
                        )
                    elif (
                        element.tag == f"{{{XLSX_NAMESPACE}}}definedName"
                        or element.attrib.get("date1904") in ("1", "true")
                    ):
                        raise ValueError(ERROR_COVERAGE)
            elif part in (XLSX_SHARED_STRINGS, XLSX_STYLES) or (
                part.endswith(".rels")
                or part == "[Content_Types].xml"
                or part.startswith("xl/theme/")
            ):
                continue
            else:
                # Comments, drawings, embedded objects and extensions need their
                # own surface adapters before this workbook can be published.
                raise ValueError(ERROR_COVERAGE)
    return NativeDocument(records=tuple(records))


def write_xlsx(
    original: Path, output: Path, replacements: dict[tuple[str, ...], str]
) -> None:
    with (
        ZipFile(original) as source,
        ZipFile(output, "w", compression=ZIP_DEFLATED) as target,
    ):
        strings = shared_strings(source)
        for part in source.namelist():
            payload = source.read(part)
            selected = {
                location[1:]: value
                for location, value in replacements.items()
                if location[0] == part
            }
            if selected or part.startswith(XLSX_WORKSHEET_PREFIX):
                root = fromstring(payload, forbid_dtd=True)
                if part.startswith(XLSX_WORKSHEET_PREFIX):
                    for cell in root.iter(f"{{{XLSX_NAMESPACE}}}c"):
                        value = selected.get((cell.attrib["r"],))
                        if value is None and cell.attrib.get("t") == "s":
                            value = strings[
                                int(
                                    cell.findtext(
                                        f"{{{XLSX_NAMESPACE}}}v", default="-1"
                                    )
                                )
                            ]
                        if value is not None:
                            for child in tuple(cell):
                                cell.remove(child)
                            cell.set("t", "inlineStr")
                            inline = SubElement(cell, f"{{{XLSX_NAMESPACE}}}is")
                            text = SubElement(inline, f"{{{XLSX_NAMESPACE}}}t")
                            text.text = value
                else:
                    for index, element in enumerate(root.iter()):
                        if (str(index),) in selected:
                            element.text = selected[(str(index),)]
                        for attribute in tuple(element.attrib):
                            if (str(index), attribute) in selected:
                                element.set(
                                    attribute, selected[(str(index), attribute)]
                                )
                payload = tostring(root, encoding="utf-8", xml_declaration=True)
            elif part == XLSX_SHARED_STRINGS:
                payload = tostring(
                    Element(
                        f"{{{XLSX_NAMESPACE}}}sst", {"count": "0", "uniqueCount": "0"}
                    )
                )
            # Rebuild the ZIP so deleted bytes, archive comments, member comments
            # and timestamp metadata do not survive from the original container.
            entry = ZipInfo(part, date_time=ZIP_FIXED_TIMESTAMP)
            entry.compress_type = ZIP_DEFLATED
            target.writestr(entry, payload)


def shared_strings(archive: ZipFile) -> tuple[str, ...]:
    if XLSX_SHARED_STRINGS not in archive.namelist():
        return ()
    root = fromstring(archive.read(XLSX_SHARED_STRINGS), forbid_dtd=True)
    return tuple("".join(node.itertext()) for node in root)


def date_styles(archive: ZipFile) -> frozenset[int]:
    root = fromstring(archive.read(XLSX_STYLES), forbid_dtd=True)
    custom = {
        int(element.attrib["numFmtId"]): element.attrib["formatCode"]
        for element in root.findall(f".//{{{XLSX_NAMESPACE}}}numFmt")
    }
    formats = root.find(f"{{{XLSX_NAMESPACE}}}cellXfs")
    if formats is None:
        raise ValueError(ERROR_STRUCTURE)
    result = set()
    for index, element in enumerate(formats):
        identifier = int(element.attrib.get("numFmtId", "0"))
        pattern = custom.get(identifier, "")
        if identifier in XLSX_DATE_FORMAT_IDS or re.search(r"(?i)[yd]", pattern):
            result.add(index)
    return frozenset(result)


def cell_value(cell: Element, strings: tuple[str, ...], dates: frozenset[int]) -> str:
    if cell.find(f"{{{XLSX_NAMESPACE}}}f") is not None:
        raise ValueError(ERROR_COVERAGE)
    if cell.attrib.get("t") == "inlineStr":
        return "".join(node.text or "" for node in cell.iter(f"{{{XLSX_NAMESPACE}}}t"))
    value = cell.findtext(f"{{{XLSX_NAMESPACE}}}v", default="")
    if not value:
        return ""
    if cell.attrib.get("t") == "s":
        return strings[int(value)]
    if int(cell.attrib.get("s", "0")) in dates:
        instant = datetime(*XLSX_EPOCH) + timedelta(days=float(value))
        if instant.time() == datetime.min.time():
            return instant.date().isoformat()
        return instant.isoformat(timespec="seconds")
    return value


def column_letters(coordinate: str) -> str:
    match = re.fullmatch(r"([A-Z]+)[1-9][0-9]*", coordinate)
    if match is None:
        raise ValueError(ERROR_STRUCTURE)
    return match[1]


def single_cell(part: str, location: str, value: str) -> NativeRecord:
    return NativeRecord(
        values=(value,),
        policies=(ColumnPolicy(index=0, kind=FIELD_TEXT),),
        locations=((part, location),),
    )
