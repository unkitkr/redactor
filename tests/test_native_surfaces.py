"""Unmodeled Office surfaces cannot be laundered through a successful cell pass."""

from pathlib import Path
from xml.etree.ElementTree import SubElement, fromstring, tostring
from zipfile import ZipFile

import pytest

from redactor.formats.xlsx import read_xlsx, write_xlsx
from redactor.schemas.configuration import ResourceSettings
from redactor.utils.constants import XLSX_NAMESPACE
from redactor.verification.xlsx import check_xlsx_surfaces


def test_xlsx_verifier_rejects_hidden_text_and_attributes(tmp_path: Path) -> None:
    original = Path(__file__).parents[1] / "input" / "billing_export.csv"
    clean = tmp_path / "original.xlsx"
    write_xlsx(original, clean, {})
    resources = ResourceSettings()
    check_xlsx_surfaces(clean, read_xlsx(clean, resources))
    with ZipFile(clean) as archive:
        parts = {part: archive.read(part) for part in archive.namelist()}
    sheet = "xl/worksheets/sheet1.xml"
    header = fromstring(parts[sheet])
    SubElement(
        SubElement(header, f"{{{XLSX_NAMESPACE}}}headerFooter"),
        f"{{{XLSX_NAMESPACE}}}oddHeader",
    ).text = "Jane Smith"
    attribute = fromstring(parts[sheet])
    properties = attribute.find(f"{{{XLSX_NAMESPACE}}}sheetPr")
    assert properties is not None
    properties.set("codeName", "Jane Smith")
    for index, replacement in enumerate(
        (
            tostring(header),
            tostring(attribute),
        )
    ):
        assert replacement != parts[sheet]
        changed = tmp_path / f"hidden-{index}.xlsx"
        with ZipFile(changed, "w") as archive:
            for part, payload in parts.items():
                archive.writestr(part, replacement if part == sheet else payload)
        with pytest.raises(ValueError, match="incomplete_surface_coverage"):
            check_xlsx_surfaces(changed, read_xlsx(changed, resources))


def test_hl7_preserves_declared_separators_and_checks_unexposed_fields(
    tmp_path: Path,
) -> None:
    from redactor.formats.hl7 import read_hl7
    from redactor.formats.hl7_encoding import write_hl7
    from redactor.verification.hl7 import check_hl7_surfaces

    source = Path(__file__).parents[1] / "input" / "adt_a01.hl7"
    output = tmp_path / "message.hl7"
    document = read_hl7(source, "utf-8")
    write_hl7(source, output, {}, "utf-8")
    assert output.read_bytes() == source.read_bytes()
    check_hl7_surfaces(source, output, document, "utf-8")
    output.write_bytes(output.read_bytes().replace(b"|P|2.5.1", b"|T|2.5.1"))
    with pytest.raises(ValueError, match="clinical_content_changed"):
        check_hl7_surfaces(source, output, document, "utf-8")
    output.write_bytes(source.read_bytes() + b"ZPI|Unassessed private extension\r")
    with pytest.raises(ValueError, match="incomplete_surface_coverage"):
        read_hl7(output, "utf-8")
