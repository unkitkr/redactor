"""Unmodeled Office surfaces cannot be laundered through a successful cell pass."""

from pathlib import Path
from zipfile import ZipFile

import pytest

from redactor.formats.xlsx import read_xlsx, write_xlsx
from redactor.schemas.configuration import ResourceSettings
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
    for index, replacement in enumerate(
        (
            parts[sheet].replace(
                b"</ns0:worksheet>",
                b"<ns0:headerFooter><ns0:oddHeader>Jane Smith</ns0:oddHeader>"
                b"</ns0:headerFooter></ns0:worksheet>",
            ),
            parts[sheet].replace(
                b"<ns0:sheetPr>", b'<ns0:sheetPr codeName="Jane Smith">'
            ),
        )
    ):
        assert replacement != parts[sheet]
        changed = tmp_path / f"hidden-{index}.xlsx"
        with ZipFile(changed, "w") as archive:
            for part, payload in parts.items():
                archive.writestr(part, replacement if part == sheet else payload)
        with pytest.raises(ValueError, match="incomplete_surface_coverage"):
            check_xlsx_surfaces(changed, read_xlsx(changed, resources))
