"""Real PDF round trips cover text, auxiliary surfaces and raster preservation."""

from io import BytesIO
from pathlib import Path

import pymupdf
import pytest
from PIL import Image

from redactor.formats.pdf import read_pdf, write_pdf
from redactor.schemas.configuration import ResourceSettings
from redactor.utils.errors import ERROR_COVERAGE, ERROR_STRUCTURE
from redactor.verification.pdf import check_pdf_structure


def test_pdf_native_rewrite_removes_source_text_and_preserves_geometry(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source.pdf"
    saved = tmp_path / "saved.pdf"
    pixel_stream = BytesIO()
    Image.new("RGB", (80, 40), "white").save(pixel_stream, format="PNG")
    with pymupdf.open() as pdf:
        page = pdf.new_page()
        page.insert_text((50, 60), "Patient: Alice Example", fontsize=11)
        page.insert_text((50, 90), "Glucose 42 mg/dL", fontsize=11)
        page.draw_line((50, 110), (250, 110))
        page.insert_image(
            pymupdf.Rect(50, 130, 130, 170), stream=pixel_stream.getvalue()
        )
        for item in page.get_images(full=True):
            pdf.xref_set_key(item[0], "ColorSpace", "/DeviceRGB")
        annotation = page.add_text_annot((200, 200), "Alice Example")
        annotation.set_info(title="Alice Example", subject="Clinical note")
        widget = pymupdf.Widget()
        widget.field_name = "patient"
        widget.field_value = "Alice Example"
        widget.field_type = pymupdf.PDF_WIDGET_TYPE_TEXT  # type: ignore[attr-defined]
        widget.rect = pymupdf.Rect(50, 220, 250, 245)
        page.add_widget(widget)
        pdf.set_metadata({"author": "Alice Example", "subject": "Glucose"})
        pdf.set_toc([[1, "Alice Example", 1]])
        pdf.set_xml_metadata(
            '<x:xmpmeta xmlns:x="adobe:ns:meta/" '
            'xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#" '
            'xmlns:dc="http://purl.org/dc/elements/1.1/">'
            "<rdf:RDF><rdf:Description><dc:title><rdf:Alt>"
            "<rdf:li>Alice Example</rdf:li></rdf:Alt></dc:title>"
            "</rdf:Description></rdf:RDF></x:xmpmeta>"
        )
        pdf.embfile_add(
            "clinical.txt",
            b"Patient: Alice Example\nGlucose 42 mg/dL",
            desc="Alice Example",
        )
        pdf.save(source)
    original_bytes = source.read_bytes()
    document = read_pdf(source, ResourceSettings())
    replacements = {
        location: value.replace("Alice Example", "Morgan Rowan")
        for record in document.records
        for location, value in zip(record.locations, record.values, strict=True)
    }
    pixels = Image.open(BytesIO(document.images[0].content)).convert("RGB")
    pixels.paste("black", (0, 0, 20, 20))
    stream = BytesIO()
    pixels.save(stream, format="PNG")
    write_pdf(
        source, saved, replacements, {document.images[0].location: stream.getvalue()}
    )
    written = read_pdf(saved, ResourceSettings())
    assert source.read_bytes() == original_bytes
    assert len(document.records) == len(written.records)
    for before, after in zip(document.records, written.records, strict=True):
        assert before.locations == after.locations
        assert before.policies == after.policies
        assert after.values == tuple(
            replacements[location] for location in before.locations
        )
    assert written.images[0].content == stream.getvalue()
    check_pdf_structure(source, saved, document)
    with pymupdf.open(saved) as pdf:
        decoded = b"".join(
            pdf.xref_stream(xref) or b""
            for xref in range(1, pdf.xref_length())
            if pdf.xref_is_stream(xref)
        )
        dictionaries = "".join(
            pdf.xref_object(xref) for xref in range(1, pdf.xref_length())
        )
        assert b"Alice Example" not in decoded
        assert "Alice Example" not in dictionaries
        assert "Glucose 42 mg/dL" in pdf[0].get_text()
    broken = tmp_path / "broken.pdf"
    with pymupdf.open(saved) as pdf:
        pdf[0].draw_line((40, 300), (240, 300))
        pdf.save(broken)
    with pytest.raises(ValueError, match=ERROR_STRUCTURE):
        check_pdf_structure(source, broken, document)


def test_pdf_unsupported_actions_and_nontext_attachments_fail_closed(
    tmp_path: Path,
) -> None:
    for binary in (False, True):
        source = tmp_path / f"unsupported-{binary}.pdf"
        with pymupdf.open() as pdf:
            pdf.new_page().insert_text((50, 50), "Clinical note")
            if binary:
                pdf.embfile_add("nested.bin", b"\x00\xff\x00")
            else:
                pdf.xref_set_key(
                    pdf.pdf_catalog(), "OpenAction", "<< /S /JavaScript /JS (unsafe) >>"
                )
            pdf.save(source)
        with pytest.raises(ValueError, match=ERROR_COVERAGE):
            read_pdf(source, ResourceSettings())
