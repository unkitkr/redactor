"""Native Word files retain formatting and account for hidden package surfaces."""

import base64
import json
import os
import subprocess
import sys
from pathlib import Path
from zipfile import ZipFile

import pytest
from lxml import etree

from redactor.formats.docx import parse_word_xml, read_docx, write_docx
from redactor.policy.identifiers import canonical_uuid, replace_identifier
from redactor.schemas.configuration import ResourceSettings
from redactor.utils.constants import (
    DOCX_CUSTOM_XML_ITEM_ID_NAMESPACE,
    DOCX_DATASTORE_ITEM_ID_ATTRIBUTE,
    DOCX_STORE_ITEM_ID_ATTRIBUTE,
    DOCX_WORD_NAMESPACE,
)
from redactor.verification.docx import check_docx_structure


def _package(path: Path, document: str, extra: dict[str, bytes] | None = None) -> None:
    parts = {
        "[Content_Types].xml": (
            b'<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            b'<Default Extension="xml" ContentType="application/xml"/>'
            b'<Default Extension="rels" ContentType="application/'
            b'vnd.openxmlformats-package.relationships+xml"/>'
            b'<Override PartName="/word/document.xml" ContentType="application/'
            b'vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
            b"</Types>"
        ),
        "_rels/.rels": (
            b'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            b'<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/'
            b'officeDocument/2006/relationships/officeDocument" '
            b'Target="word/document.xml"/>'
            b"</Relationships>"
        ),
        "word/document.xml": document.encode(),
    }
    parts.update(extra or {})
    with ZipFile(path, "w") as archive:
        for name, content in parts.items():
            archive.writestr(name, content)


def test_word_pipeline_coalesces_separate_demographics_and_replays(
    tmp_path: Path,
) -> None:
    source = tmp_path / "input"
    source.mkdir()
    original = source / "letter.docx"
    _package(
        original,
        f'<w:document xmlns:w="{DOCX_WORD_NAMESPACE}"><w:body>'
        "<w:p>"
        "<w:r>"
        "<w:rPr>"
        "<w:b/>"
        "</w:rPr>"
        "<w:t>Patient: Amina </w:t>"
        "</w:r>"
        "<w:r>"
        "<w:t>Keller</w:t>"
        "</w:r>"
        "</w:p>"
        "<w:p><w:r><w:t>MRN: 74208</w:t></w:r></w:p>"
        "<w:p><w:r><w:t>DOB: 1972-03-04</w:t></w:r></w:p>"
        "<w:p><w:r><w:t>Discharge: 2024-03-12</w:t></w:r></w:p>"
        "<w:p><w:r><w:t>Glucose 120 mg/dL.</w:t></w:r></w:p>"
        "</w:body></w:document>",
    )
    document = read_docx(original, ResourceSettings())
    evidence = [
        record.evidence.patient for record in document.records if record.evidence
    ]
    assert evidence and all(
        person
        and person.identifier == "74208"
        and person.name == "Amina Keller"
        and person.birth_date
        for person in evidence
    )
    config = tmp_path / "settings.toml"
    config.write_text('[local]\nner = "spacy"\n')
    state = tmp_path / "run/.redactor"
    outputs: list[bytes] = []
    for _ in range(2):
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "redactor",
                "--input",
                str(source),
                "--state",
                str(state),
                "--config",
                str(config),
                "--no-dashboard",
            ],
            env=dict(
                os.environ,
                REDACTOR_SECRET_KEY=base64.b64encode(bytes(range(32))).decode(),
                LLM_ENABLED="0",
            ),
            capture_output=True,
            text=True,
            timeout=45,
        )
        assert result.returncode == 0, result.stderr
        report = json.loads((tmp_path / "run/output/report.json").read_text())
        assert report["published"] == 1, report
        saved = tmp_path / "run/output/published/letter.docx"
        outputs.append(saved.read_bytes())
        check_docx_structure(original, saved)
        with ZipFile(saved) as archive:
            payload = archive.read("word/document.xml")
            assert b"Amina" not in payload and b"Keller" not in payload
            assert b"Glucose 120 mg/dL." in payload
    assert outputs[0] == outputs[1]


def test_word_hidden_surfaces_nested_paragraphs_and_structure(tmp_path: Path) -> None:
    original, output = tmp_path / "original.docx", tmp_path / "saved.docx"
    _package(
        original,
        f'<w:document xmlns:w="{DOCX_WORD_NAMESPACE}"><w:body>'
        "<w:p>"
        "<w:r>"
        "<w:t>Visible Alice</w:t>"
        "</w:r>"
        "<w:r>"
        "<w:drawing>"
        "<w:txbxContent>"
        "<w:p>"
        "<w:r>"
        "<w:t>Nested Beth</w:t>"
        "</w:r>"
        "</w:p>"
        "</w:txbxContent>"
        "</w:drawing>"
        "</w:r>"
        '<w:del w:author="Deleted Author">'
        "<w:r>"
        "<w:delText>Deleted Chris</w:delText>"
        "</w:r>"
        "</w:del>"
        "</w:p>"
        "<!-- Hidden Diane -->"
        "<w:p>"
        "<w:r>"
        "<w:rPr>"
        '<w:sz w:val="24"/>'
        "</w:rPr>"
        "<w:t>Final Eve</w:t>"
        "</w:r>"
        "</w:p>"
        "</w:body></w:document>",
        {
            "customXml/item2.xml": (
                b"<record>"
                b"<patient_name>Farah Green</patient_name>"
                b"<mrn>9988</mrn>"
                b"<dob>1970-01-01</dob>"
                b"</record>"
            )
        },
    )
    doc = read_docx(original, ResourceSettings())
    values = [value for record in doc.records for value in record.values]
    assert values.count("Nested Beth") == 1
    assert "Visible Alice" in values and "Deleted Chris" in values
    assert "Deleted Author" in values and " Hidden Diane " in values
    changes = {
        location: value.replace("Alice", "Robin")
        .replace("Beth", "River")
        .replace("Chris", "Alex")
        .replace("Diane", "Terry")
        for record in doc.records
        for location, value in zip(record.locations, record.values, strict=True)
        if any(name in value for name in ("Alice", "Beth", "Chris", "Diane"))
    }
    write_docx(original, output, changes, {})
    check_docx_structure(original, output)
    with ZipFile(output) as archive:
        parts = {name: archive.read(name) for name in archive.namelist()}
    root = parse_word_xml(parts["word/document.xml"])
    size = next(root.iter(f"{{{DOCX_WORD_NAMESPACE}}}sz"))
    size.set(f"{{{DOCX_WORD_NAMESPACE}}}val", "30")
    parts["word/document.xml"] = etree.tostring(root)
    tampered = tmp_path / "tampered.docx"
    with ZipFile(tampered, "w") as archive:
        for name, payload in parts.items():
            archive.writestr(name, payload)
    normalized = tmp_path / "normalized.docx"
    write_docx(tampered, normalized, {}, {})
    with pytest.raises(ValueError, match="clinical_content_changed"):
        check_docx_structure(original, normalized)


def test_word_document_subject_requires_declared_corroborated_context(
    tmp_path: Path,
) -> None:
    for index, (root_name, name, linked) in enumerate(
        (
            ("patientContext", "Amina Keller", True),
            ("otherPerson", "Amina Keller", False),
            ("patientContext", "Nadia Velez", False),
        )
    ):
        path = tmp_path / f"context-{index}.docx"
        _package(
            path,
            f'<w:document xmlns:w="{DOCX_WORD_NAMESPACE}"><w:body>'
            "<w:p><w:r><w:t>Patient: Amina Keller</w:t></w:r></w:p>"
            "</w:body></w:document>",
            {
                "customXml/item3.xml": (
                    f"<{root_name}><name>{name}</name><mrn>98745</mrn>"
                    f"<dob>1972-04-11</dob></{root_name}>"
                ).encode()
            },
        )
        document = read_docx(path, ResourceSettings())
        body = next(
            record
            for record in document.records
            if record.context_scope == "word/document.xml"
        )
        assert body.evidence and body.evidence.patient
        assert bool(body.evidence.patient.identifier) is linked
        assert bool(body.evidence.patient.birth_date) is linked


def test_word_drops_optional_private_thumbnail_and_keeps_document_image(
    tmp_path: Path,
) -> None:
    source = tmp_path / "with-preview.docx"
    output = tmp_path / "without-preview.docx"
    _package(
        source,
        f'<w:document xmlns:w="{DOCX_WORD_NAMESPACE}"><w:body>'
        "<w:p><w:r><w:t>Clinical text.</w:t></w:r></w:p>"
        "</w:body></w:document>",
        {
            "docProps/thumbnail.jpeg": b"Private preview: patient Amina Keller",
            "word/media/image1.png": b"Main image stays on the image assessment path",
            "word/_rels/document.xml.rels": (
                b'<Relationships xmlns="http://schemas.openxmlformats.org/'
                b'package/2006/relationships"><Relationship Id="rId1" '
                b'Type="http://schemas.openxmlformats.org/officeDocument/2006/'
                b'relationships/image" Target="media/image1.png"/></Relationships>'
            ),
        },
    )
    with ZipFile(source) as archive:
        parts = {name: archive.read(name) for name in archive.namelist()}
    parts["_rels/.rels"] = parts["_rels/.rels"].replace(
        b"</Relationships>",
        b'<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/'
        b'package/2006/relationships/metadata/thumbnail" '
        b'Target="docProps/thumbnail.jpeg"/></Relationships>',
    )
    parts["[Content_Types].xml"] = parts["[Content_Types].xml"].replace(
        b"</Types>", b'<Default Extension="jpeg" ContentType="image/jpeg"/></Types>'
    )
    with ZipFile(source, "w") as archive:
        for name, content in parts.items():
            archive.writestr(name, content)
    document = read_docx(source, ResourceSettings())
    assert [image.location for image in document.images] == [
        ("image", "word/media/image1.png")
    ]
    write_docx(source, output, {}, {})
    check_docx_structure(source, output)
    with ZipFile(output) as archive:
        assert "docProps/thumbnail.jpeg" not in archive.namelist()
        assert b"thumbnail" not in archive.read("_rels/.rels")
        assert b'Extension="jpeg"' not in archive.read("[Content_Types].xml")
        assert archive.read("word/media/image1.png") == parts["word/media/image1.png"]
    altered = tmp_path / "lost-image.docx"
    with ZipFile(output) as source_archive, ZipFile(altered, "w") as archive:
        for name in source_archive.namelist():
            if name != "word/media/image1.png":
                archive.writestr(name, source_archive.read(name))
    normalized = tmp_path / "lost-image-clean.docx"
    write_docx(altered, normalized, {}, {})
    with pytest.raises(ValueError, match="incomplete_surface_coverage"):
        check_docx_structure(source, normalized)


@pytest.mark.parametrize("prefix", ("ds", "ns7"))
def test_word_uuid_rewrites_preserve_binding_targets_and_reject_tampering(
    tmp_path: Path, prefix: str
) -> None:
    source, saved = tmp_path / "source.docx", tmp_path / "saved.docx"
    ids = (
        "{46A604F0-8498-42F8-8CEC-51942E2AD573}",
        "{69E6B16C-9309-4A9D-83D1-60EDC071359B}",
    )
    namespace = DOCX_DATASTORE_ITEM_ID_ATTRIBUTE[1:].split("}")[0]
    clinical = "Glucose 103 mg/dL. Metformin 500 mg BID."
    body = "".join(
        f'<w:sdt><w:sdtPr><w:dataBinding w:storeItemID="{value.lower()}" '
        f'w:xpath="/record/value"/></w:sdtPr><w:sdtContent><w:p><w:r>'
        f"<w:t>{clinical}</w:t></w:r></w:p></w:sdtContent></w:sdt>"
        for value in (ids[0], ids[1], ids[0])
    )
    properties = {
        f"customXml/itemProps{index}.xml": (
            f'<{prefix}:datastoreItem xmlns:{prefix}="{namespace}" '
            f'{prefix}:itemID="{value}"/>'
        ).encode()
        for index, value in enumerate(ids, 1)
    }
    _package(
        source,
        f'<w:document xmlns:w="{DOCX_WORD_NAMESPACE}"><w:body>{body}'
        "</w:body></w:document>",
        properties,
    )
    original_bytes = source.read_bytes()
    document = read_docx(source, ResourceSettings())
    changes = {
        location: replace_identifier(
            value, bytes(range(32)), namespace=policy.namespace
        )
        for record in document.records
        for value, location, policy in zip(
            record.values, record.locations, record.policies, strict=True
        )
        if policy.namespace == DOCX_CUSTOM_XML_ITEM_ID_NAMESPACE
    }
    assert len(changes) == 5
    assert len({canonical_uuid(value) for value in changes.values()}) == 2
    write_docx(source, saved, changes, {})
    check_docx_structure(source, saved)
    with ZipFile(saved) as archive:
        parts = {name: archive.read(name) for name in archive.namelist()}
    assert parts["word/document.xml"].count(clinical.encode()) == 3
    assert all(
        value.encode() not in content.upper()
        for value in ids
        for content in parts.values()
    )
    assert source.read_bytes() == original_bytes
    read_docx(saved, ResourceSettings(), extract_evidence=False)
    replay = tmp_path / "replayed.docx"
    write_docx(source, replay, changes, {})
    assert replay.read_bytes() == saved.read_bytes()

    # Switching a binding to another existing item is valid UUID syntax but
    # changes the document's data source and must fail the structural check.
    root = parse_word_xml(parts["word/document.xml"])
    bindings = list(root.iter(f"{{{DOCX_WORD_NAMESPACE}}}dataBinding"))
    bindings[0].set(
        DOCX_STORE_ITEM_ID_ATTRIBUTE,
        bindings[1].attrib[DOCX_STORE_ITEM_ID_ATTRIBUTE],
    )
    altered_parts = dict(parts)
    altered_parts["word/document.xml"] = etree.tostring(root)
    altered, normalized = tmp_path / "altered.docx", tmp_path / "normalized.docx"
    with ZipFile(altered, "w") as archive:
        for name, payload in altered_parts.items():
            archive.writestr(name, payload)
    write_docx(altered, normalized, {}, {})
    with pytest.raises(ValueError, match="incomplete_surface_coverage"):
        check_docx_structure(source, normalized)

    # A malformed, duplicate or missing definition never becomes an exempt
    # schema identifier merely because it occupies a familiar attribute.
    for replacement in (ids[0][1:], ids[1], "Patient Amina Keller"):
        broken = tmp_path / "broken.docx"
        with ZipFile(source) as original, ZipFile(broken, "w") as archive:
            for name in original.namelist():
                payload = original.read(name)
                if name == "customXml/itemProps1.xml":
                    payload = payload.replace(ids[0].encode(), replacement.encode())
                archive.writestr(name, payload)
        with pytest.raises(ValueError):
            read_docx(broken, ResourceSettings())

    # Identically named attributes in an unknown namespace remain free text.
    unrelated = tmp_path / "unrelated.docx"
    _package(
        unrelated,
        f'<w:document xmlns:w="{DOCX_WORD_NAMESPACE}"><w:body>'
        f'<w:p xmlns:ns8="urn:example:custom" ns8:itemID="{ids[0]}">'
        f"<w:r><w:t>{clinical}</w:t></w:r></w:p></w:body></w:document>",
    )
    exposed = read_docx(unrelated, ResourceSettings())
    assert any(
        value == ids[0] and policy.kind == "text" and not policy.namespace
        for record in exposed.records
        for value, policy in zip(record.values, record.policies, strict=True)
    )
