"""Reject identifying XML names and metadata, even when their values look structural."""

from pathlib import Path
from zipfile import ZipFile

import pytest

from redactor.formats.xlsx import read_xlsx, write_xlsx
from redactor.schemas.configuration import ResourceSettings
from redactor.verification.xlsx import check_xlsx_surfaces
from redactor.verification.xlsx_source import check_xlsx_source_surfaces


def test_office_vocabulary_rejects_unknown_carriers_and_structural_url_suffixes(
    tmp_path: Path,
) -> None:
    clean = tmp_path / "clean.xlsx"
    write_xlsx(Path(__file__).parents[1] / "input/billing_export.csv", clean, {})
    resources = ResourceSettings()
    document = read_xlsx(clean, resources)
    check_xlsx_surfaces(clean, document)
    check_xlsx_source_surfaces(clean, document)
    with ZipFile(clean) as archive:
        parts = {name: archive.read(name) for name in archive.namelist()}

    styles = parts["xl/styles.xml"]
    mutations = [
        (
            "xl/styles.xml",
            styles.replace(b"</styleSheet>", b"<Patient-Renee-Ward/></styleSheet>"),
        ),
        (
            "xl/styles.xml",
            styles.replace(b"<styleSheet ", b'<styleSheet patientId="123456789" ', 1),
        ),
        (
            "xl/styles.xml",
            styles.replace(b"<styleSheet ", b'<styleSheet val="123456789" ', 1),
        ),
        (
            "xl/styles.xml",
            styles.replace(
                b"<styleSheet ",
                b'<styleSheet xmlns:private="urn:patient:Renee-Ward" ',
                1,
            ),
        ),
        (
            "xl/styles.xml",
            styles.replace(
                b"<styleSheet ",
                b'<styleSheet xmlns:PatientRenee="http://schemas.openxmlformats.org/'
                b'spreadsheetml/2006/main" ',
                1,
            ),
        ),
        (
            "xl/styles.xml",
            styles.replace(
                b"<styleSheet ",
                b'<styleSheet private="http://schemas.openxmlformats.org/'
                b'patient/Renee-Ward" ',
                1,
            ),
        ),
        (
            "xl/styles.xml",
            styles.replace(
                b"</styleSheet>",
                b'<a:PatientRenee xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"/></styleSheet>',
            ),
        ),
        (
            "_rels/.rels",
            parts["_rels/.rels"].replace(
                b'relationships/officeDocument"',
                b'relationships/officeDocument/patient/Renee-Ward"',
            ),
        ),
        (
            "[Content_Types].xml",
            parts["[Content_Types].xml"].replace(
                b'application/xml"', b'application/xml/patient/Renee-Ward"'
            ),
        ),
    ]
    for number, (part, payload) in enumerate(mutations):
        assert payload != parts[part]
        changed = tmp_path / f"carrier-{number}.xlsx"
        with ZipFile(changed, "w") as archive:
            for name, original in parts.items():
                archive.writestr(name, payload if name == part else original)
        with pytest.raises(ValueError):
            check_xlsx_surfaces(changed, read_xlsx(changed, resources))

    changed = tmp_path / "identifying-part-name.xlsx"
    with ZipFile(changed, "w") as archive:
        for name, payload in parts.items():
            archive.writestr(name, payload)
        archive.writestr("xl/theme/Patient-Renee-Ward.xml", b"<empty/>")
    with pytest.raises(ValueError):
        check_xlsx_surfaces(changed, read_xlsx(changed, resources))
