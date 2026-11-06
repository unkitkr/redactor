"""Publish an independently built workbook and reject unassessed comment carriers."""

import base64
import json
import os
import subprocess
import sys
from pathlib import Path
from xml.etree.ElementTree import SubElement, fromstring, tostring
from zipfile import ZipFile

import pytest
from openpyxl import load_workbook

from redactor.formats.xlsx import read_xlsx
from redactor.schemas.configuration import ResourceSettings
from redactor.verification.xlsx import check_xlsx_surfaces
from redactor.verification.xlsx_preservation import check_xlsx_preservation
from redactor.verification.xlsx_source import check_xlsx_source_surfaces


def test_workbook_comment_runs_authors_and_hidden_sheets_round_trip(
    tmp_path: Path,
) -> None:
    source = tmp_path / "input"
    source.mkdir()
    original = source / "study.xlsx"
    _make_workbook(original)
    with ZipFile(original) as archive:
        source_parts = {name: archive.read(name) for name in archive.namelist()}
    for name, part, payload in (
        (
            "bad-style.xlsx",
            "xl/styles.xml",
            source_parts["xl/styles.xml"].replace(
                b'<xf numFmtId="0"',
                b'<xf numFmtId="0" fontId="99"',
            ),
        ),
        (
            "bad-range.xlsx",
            "xl/workbook.xml",
            source_parts["xl/workbook.xml"].replace(
                b"'Marisol Bennett'!$A$2",
                b"'Missing sheet'!$A$2",
            ),
        ),
    ):
        assert payload != source_parts[part]
        with ZipFile(source / name, "w") as archive:
            for member, content in source_parts.items():
                archive.writestr(member, payload if member == part else content)
    configuration = tmp_path / "settings.toml"
    configuration.write_text('[local]\nner = "spacy"\n')
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "redactor",
            "--input",
            str(source),
            "--state",
            str(tmp_path / ".redactor"),
            "--config",
            str(configuration),
            "--no-dashboard",
        ],
        env=dict(
            os.environ,
            REDACTOR_SECRET_KEY=base64.b64encode(bytes(range(32))).decode(),
            LLM_ENABLED="0",
        ),
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    output = tmp_path / "output"
    report = json.loads((output / "report.json").read_text())
    assert report["published"] == 1, report
    assert report["quarantined"] == 2, report
    saved = output / "published/study.xlsx"
    resources = ResourceSettings()
    document = read_xlsx(saved, resources)
    check_xlsx_surfaces(saved, document)
    check_xlsx_source_surfaces(original, read_xlsx(original, resources))
    check_xlsx_preservation(original, saved, read_xlsx(original, resources))
    with ZipFile(saved) as archive:
        parts = {name: archive.read(name) for name in archive.namelist()}
    joined = b"".join(parts.values())
    for identifier in (
        b"Marisol",
        b"Bennett",
        b"Anika",
        b"Voss",
        b"PrivateRelationship",
        b"Person_Amara_Vale",
    ):
        assert identifier not in joined
    comment = fromstring(parts["xl/comments/comment1.xml"])
    assert "Creatinine 1.2 mg/dL." in "".join(comment.itertext())
    assert b'val="1"' in parts["xl/comments/comment1.xml"]
    assert b'state="hidden"' in parts["xl/workbook.xml"]
    assert b">1.20<" in parts["xl/worksheets/sheet1.xml"]
    workbook = load_workbook(saved)
    try:
        assert workbook.worksheets[0]["A2"].value == 1.2
        assert workbook.worksheets[1].sheet_state == "hidden"
        names = tuple(workbook.defined_names.values())
        assert len(names) == 1 and names[0].name.startswith("range_")
        assert tuple(names[0].destinations) == ((workbook.worksheets[0].title, "$A$2"),)
    finally:
        workbook.close()
    workbook_part = "xl/workbook.xml"
    changed_range = tmp_path / "changed-range.xlsx"
    with ZipFile(changed_range, "w") as archive:
        for member, content in parts.items():
            archive.writestr(
                member,
                content.replace(b"!$A$2", b"!$A$3")
                if member == workbook_part
                else content,
            )
    with pytest.raises(ValueError, match="clinical_content_changed"):
        check_xlsx_preservation(original, changed_range, read_xlsx(original, resources))
    comments = "xl/comments/comment1.xml"
    drawing = "xl/drawings/commentsDrawing1.vml"
    changed_comments = fromstring(parts[comments])
    authors = changed_comments.find(
        "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}authors"
    )
    assert authors is not None
    SubElement(
        authors, "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}author"
    ).text = "Missed person"
    for index, (part, payload) in enumerate(
        (
            (
                comments,
                tostring(changed_comments),
            ),
            (drawing, parts[drawing].replace(b"<div/>", b"<div>Hidden person</div>")),
            (
                drawing,
                parts[drawing].replace(
                    b"position:absolute",
                    b"position:absolute;background:url(private.example)",
                ),
            ),
        )
    ):
        assert payload != parts[part]
        changed = tmp_path / f"tampered-{index}.xlsx"
        with ZipFile(changed, "w") as archive:
            for name, content in parts.items():
                archive.writestr(name, payload if name == part else content)
        with pytest.raises(ValueError):
            check_xlsx_surfaces(changed, document)


def _make_workbook(path: Path) -> None:
    spreadsheet = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
    office = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
    package = "http://schemas.openxmlformats.org/package/2006/relationships"
    mime = "application/vnd.openxmlformats-"
    parts = {
        "[Content_Types].xml": (
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            f'<Default Extension="rels" ContentType="{mime}package.relationships+xml"/>'
            '<Default Extension="xml" ContentType="application/xml"/>'
            f'<Default Extension="vml" ContentType="{mime}officedocument.vmlDrawing"/>'
            '<Override PartName="/xl/workbook.xml" '
            f'ContentType="{mime}officedocument.spreadsheetml.sheet.main+xml"/>'
            '<Override PartName="/xl/worksheets/sheet1.xml" '
            f'ContentType="{mime}officedocument.spreadsheetml.worksheet+xml"/>'
            '<Override PartName="/xl/worksheets/sheet2.xml" '
            f'ContentType="{mime}officedocument.spreadsheetml.worksheet+xml"/>'
            '<Override PartName="/xl/styles.xml" '
            f'ContentType="{mime}officedocument.spreadsheetml.styles+xml"/>'
            '<Override PartName="/xl/comments/comment1.xml" '
            f'ContentType="{mime}officedocument.spreadsheetml.comments+xml"/></Types>'
        ),
        "_rels/.rels": (
            f'<Relationships xmlns="{package}">'
            '<Relationship Id="PrivateRelationship" '
            f'Type="{office}/officeDocument" Target="xl/workbook.xml"/>'
            "</Relationships>"
        ),
        "xl/_rels/workbook.xml.rels": (
            f'<Relationships xmlns="{package}">'
            '<Relationship Id="PrivateRelationship" '
            f'Type="{office}/worksheet" Target="worksheets/sheet1.xml"/>'
            f'<Relationship Id="hidden" Type="{office}/worksheet" '
            'Target="worksheets/sheet2.xml"/>'
            f'<Relationship Id="styles" Type="{office}/styles" Target="styles.xml"/>'
            "</Relationships>"
        ),
        "xl/workbook.xml": (
            f'<workbook xmlns="{spreadsheet}" xmlns:r="{office}">'
            '<sheets><sheet name="Marisol Bennett" sheetId="1" state="visible" '
            'r:id="PrivateRelationship"/>'
            '<sheet name="Results" sheetId="2" state="hidden" r:id="hidden"/>'
            '</sheets><definedNames><definedName name="Person_Amara_Vale">'
            "'Marisol Bennett'!$A$2</definedName></definedNames></workbook>"
        ),
        "xl/styles.xml": (
            f'<styleSheet xmlns="{spreadsheet}">'
            '<fonts count="1"><font><name val="Calibri"/><sz val="11"/></font></fonts>'
            '<fills count="1"><fill><patternFill patternType="none"/></fill></fills>'
            '<borders count="1"><border/></borders>'
            '<cellStyleXfs count="1"><xf numFmtId="0"/></cellStyleXfs>'
            '<cellXfs count="1"><xf numFmtId="0" xfId="0"/></cellXfs>'
            '<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/>'
            "</cellStyles></styleSheet>"
        ),
        "xl/worksheets/sheet1.xml": (
            f'<worksheet xmlns="{spreadsheet}" xmlns:r="{office}">'
            '<sheetData><row r="1"><c r="A1" t="inlineStr">'
            "<is><t>lab_value</t></is></c></row>"
            '<row r="2"><c r="A2"><v>1.20</v></c></row></sheetData>'
            '<legacyDrawing r:id="PrivateRelationship"/></worksheet>'
        ),
        "xl/worksheets/sheet2.xml": (
            f'<worksheet xmlns="{spreadsheet}"><sheetData>'
            '<row r="1"><c r="A1" t="inlineStr">'
            "<is><t>lab_value</t></is></c></row>"
            '<row r="2"><c r="A2"><v>8.40</v></c></row>'
            "</sheetData></worksheet>"
        ),
        "xl/worksheets/_rels/sheet1.xml.rels": (
            f'<Relationships xmlns="{package}">'
            f'<Relationship Id="comments" Type="{office}/comments" '
            'Target="../comments/comment1.xml"/>'
            f'<Relationship Id="PrivateRelationship" Type="{office}/vmlDrawing" '
            'Target="../drawings/commentsDrawing1.vml"/></Relationships>'
        ),
        "xl/comments/comment1.xml": (
            f'<comments xmlns="{spreadsheet}">'
            "<authors><author>Anika Voss</author></authors>"
            '<commentList><comment ref="A2" authorId="0"><text>'
            '<r><rPr><b val="1"/></rPr><t>Patient: Marisol </t></r>'
            "<r><t>Bennett. Creatinine 1.2 mg/dL.</t></r>"
            "</text></comment></commentList></comments>"
        ),
        "xl/drawings/commentsDrawing1.vml": (
            '<xml xmlns:v="urn:schemas-microsoft-com:vml" '
            'xmlns:x="urn:schemas-microsoft-com:office:excel">'
            '<v:shapetype id="_x0000_t202" coordsize="21600,21600"/>'
            '<v:shape id="_x0000_s2048" type="#_x0000_t202" '
            'style="position:absolute;width:140pt;height:70pt;visibility:hidden">'
            '<v:textbox><div/></v:textbox><x:ClientData ObjectType="Note">'
            "<x:Row>1</x:Row><x:Column>0</x:Column></x:ClientData></v:shape></xml>"
        ),
    }
    with ZipFile(path, "w") as archive:
        for name, text in parts.items():
            archive.writestr(name, text.encode())
