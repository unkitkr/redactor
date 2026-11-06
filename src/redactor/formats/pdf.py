"""Bounded PDF text, raster images, metadata and plain-text attachments.

Unsupported interactive and hidden surfaces fail closed. Text redactions remove
content operators before replacement text is inserted; a fresh save removes old
objects and prior revisions.
"""

import re
import xml.etree.ElementTree as ElementTree
from io import BytesIO
from pathlib import Path
from typing import Any, cast

import pymupdf
from defusedxml.ElementTree import fromstring
from PIL import Image

from redactor.formats.text import replace_text_fields, text_record
from redactor.schemas.configuration import ResourceSettings
from redactor.schemas.native import NativeDocument, NativeImage, NativeRecord
from redactor.schemas.redaction import ColumnPolicy
from redactor.utils.constants import (
    FIELD_IDENTIFIER,
    FIELD_TEXT,
    PDF_ANNOTATION_PART,
    PDF_ATTACHMENT_PART,
    PDF_FONT_NAMES,
    PDF_GARBAGE_LEVEL,
    PDF_IMAGE_PART,
    PDF_METADATA_FIELDS,
    PDF_METADATA_PART,
    PDF_MINIMUM_FONT_SIZE,
    PDF_OUTLINE_PART,
    PDF_TEXT_PART,
    PDF_UNSUPPORTED_KEYS,
    PDF_WIDGET_PART,
    PDF_XMP_PART,
    TEXT_ENCODING,
)
from redactor.utils.errors import (
    ERROR_COVERAGE,
    ERROR_ENCRYPTED_INPUT,
    ERROR_RESOURCE_LIMIT,
    ERROR_STRUCTURE,
)


def pdf_lines(page: pymupdf.Page) -> list[dict[str, Any]]:
    """Return horizontal lines in geometric order, independent of stream order."""
    result: list[dict[str, Any]] = []
    textpage = pymupdf.TextPage(
        page.get_displaylist(annots=False).get_textpage(flags=pymupdf.TEXTFLAGS_TEXT)
    )
    for block in textpage.extractDICT()["blocks"]:
        for line in block.get("lines", []):
            spans = line["spans"]
            if not spans:
                continue
            if tuple(line["dir"]) != (1.0, 0.0) or line["wmode"]:
                raise ValueError(ERROR_COVERAGE)
            if any(span["font"] not in PDF_FONT_NAMES for span in spans):
                raise ValueError(ERROR_COVERAGE)
            text = "".join(span["text"] for span in spans)
            if any(ord(char) < 32 or ord(char) > 126 for char in text):
                raise ValueError(ERROR_COVERAGE)
            rectangle = pymupdf.Rect(line["bbox"])
            if not page.rect.contains(rectangle):
                raise ValueError(ERROR_COVERAGE)
            result.append({**line, "text": text, "origin": spans[0]["origin"]})
    return sorted(result, key=lambda line: (line["origin"][1], line["origin"][0]))


def validate_pdf_surfaces(document: pymupdf.Document) -> None:
    """Reject populated PDF surfaces not represented by the native contract."""
    if document.needs_pass or document.is_encrypted:
        raise ValueError(ERROR_ENCRYPTED_INPUT)
    if not document.is_pdf or document.is_repaired or not len(document):
        raise ValueError(ERROR_STRUCTURE)
    forbidden = re.compile(r"/(?:" + "|".join(PDF_UNSUPPORTED_KEYS) + r")\b")
    info_reference = document.xref_get_key(-1, "Info")
    info_xref = int(info_reference[1].split()[0]) if info_reference[0] == "xref" else 0
    for xref in range(1, document.xref_length()):
        description = document.xref_object(xref)
        if forbidden.search(description):
            raise ValueError(ERROR_COVERAGE)
        keys = document.xref_get_keys(xref)
        # Arbitrary object strings are not a supported metadata channel.
        for key in keys:
            kind, _ = document.xref_get_key(xref, key)
            if (
                kind == "string"
                and xref != info_xref
                and key
                not in (
                    "F",
                    "UF",
                    "Desc",
                    "CheckSum",
                    "CreationDate",
                    "ModDate",
                    "Title",
                    "Author",
                    "Subject",
                    "Subj",
                    "M",
                    "Contents",
                    "T",
                    "TU",
                    "V",
                    "DV",
                    "DA",
                    "NM",
                )
            ):
                raise ValueError(ERROR_COVERAGE)
    if info_xref and set(document.xref_get_keys(info_xref)) - {
        "Title",
        "Author",
        "Subject",
        "Keywords",
        "Creator",
        "Producer",
        "CreationDate",
        "ModDate",
        "Trapped",
    }:
        raise ValueError(ERROR_COVERAGE)
    for page in document.pages():
        if (
            page.rotation
            or page.cropbox != page.mediabox
            or page.get_links()
            or page.get_xobjects()
        ):
            raise ValueError(ERROR_COVERAGE)
        if any(
            trace["type"] != 0 or trace["opacity"] != 1
            for trace in page.get_texttrace()
        ):
            raise ValueError(ERROR_COVERAGE)
        # Image masks and transparency cannot be faithfully checked as RGB pixels.
        for image in page.get_images(full=True):
            if image[1] or image[5] not in ("DeviceRGB", "DeviceGray"):
                raise ValueError(ERROR_COVERAGE)
        pdf_lines(page)
    _auxiliary_records(document)


def pdf_images(document: pymupdf.Document) -> list[tuple[int, int]]:
    """Return each raster object once, ordered by its first page occurrence."""
    images: list[tuple[int, int]] = []
    seen: set[int] = set()
    for number, page in enumerate(document.pages()):
        for entry in page.get_images(full=True):
            if entry[0] not in seen:
                images.append((number, entry[0]))
                seen.add(entry[0])
    return images


def _metadata_record(document: pymupdf.Document) -> NativeRecord:
    return NativeRecord(
        values=tuple(
            (document.metadata or {}).get(key, "") or "" for key in PDF_METADATA_FIELDS
        ),
        policies=tuple(
            ColumnPolicy(
                index=index,
                kind=FIELD_IDENTIFIER
                if key in ("creationDate", "modDate")
                else FIELD_TEXT,
                namespace=PDF_METADATA_PART
                if key in ("creationDate", "modDate")
                else "",
            )
            for index, key in enumerate(PDF_METADATA_FIELDS)
        ),
        locations=tuple((PDF_METADATA_PART, key) for key in PDF_METADATA_FIELDS),
    )


def _attachment_records(document: pymupdf.Document) -> list[NativeRecord]:
    records: list[NativeRecord] = []
    for number in range(document.embfile_count()):
        info = document.embfile_info(number)
        try:
            body = document.embfile_get(number).decode(TEXT_ENCODING)
        except UnicodeDecodeError as error:
            raise ValueError(ERROR_COVERAGE) from error
        if "\x00" in body:
            raise ValueError(ERROR_COVERAGE)
        prefix = f"{PDF_ATTACHMENT_PART}:{number}"
        records.append(text_record(body, prefix))
        fields = ("name", "filename", "ufilename", "description")
        records.append(
            NativeRecord(
                values=tuple(str(info.get(key, "")) for key in fields),
                policies=tuple(
                    ColumnPolicy(index=index, kind=FIELD_TEXT)
                    for index in range(len(fields))
                ),
                locations=tuple((prefix, key) for key in fields),
            )
        )
    return records


def read_pdf(path: Path, resources: ResourceSettings) -> NativeDocument:
    if path.stat().st_size > resources.max_native_file_bytes:
        raise ValueError(ERROR_RESOURCE_LIMIT)
    with pymupdf.open(path) as document:
        validate_pdf_surfaces(document)
        expanded = sum(
            len(document.xref_stream(xref) or b"")
            for xref in range(1, document.xref_length())
            if document.xref_is_stream(xref)
        )
        if expanded > resources.max_archive_bytes:
            raise ValueError(ERROR_RESOURCE_LIMIT)
        records = [
            text_record(
                "\n".join(line["text"] for line in pdf_lines(page)),
                f"{PDF_TEXT_PART}:{number}",
            )
            for number, page in enumerate(document.pages())
        ]
        records.append(_metadata_record(document))
        records.extend(_attachment_records(document))
        records.extend(_auxiliary_records(document))
        images: list[NativeImage] = []
        pixels = 0
        for number, (_, xref) in enumerate(pdf_images(document)):
            image = document.extract_image(xref)
            pixels += image["width"] * image["height"]
            if pixels > resources.max_image_pixels:
                raise ValueError(ERROR_RESOURCE_LIMIT)
            images.append(
                NativeImage(
                    location=(PDF_IMAGE_PART, str(number)),
                    content=_canonical_image(image["image"]),
                )
            )
        if any(
            sum(len(value.encode(TEXT_ENCODING)) for value in record.values)
            > resources.max_record_bytes
            for record in records
        ):
            raise ValueError(ERROR_RESOURCE_LIMIT)
        return NativeDocument(records=tuple(records), images=tuple(images))


def _write_page(page: pymupdf.Page, replacements: dict[tuple[str, ...], str]) -> None:
    lines = pdf_lines(page)
    original = "\n".join(line["text"] for line in lines)
    replacement = replace_text_fields(
        original, replacements, f"{PDF_TEXT_PART}:{page.number}"
    )
    changed = replacement.split("\n") if lines else []
    if len(changed) != len(lines):
        raise ValueError(ERROR_COVERAGE)
    inserts: list[tuple[dict[str, Any], str, float]] = []
    for line, text in zip(lines, changed, strict=True):
        if text == line["text"]:
            continue
        if any(ord(char) < 32 or ord(char) > 126 for char in text):
            raise ValueError(ERROR_COVERAGE)
        rectangle = pymupdf.Rect(line["bbox"])
        if any(
            rectangle.intersects(pymupdf.Rect(other["bbox"]))
            for other in lines
            if other is not line
        ):
            raise ValueError(ERROR_COVERAGE)
        size = min(float(span["size"]) for span in line["spans"])
        width = pymupdf.get_text_length(text, fontname="helv", fontsize=size)
        if width > rectangle.width and width:
            size *= rectangle.width / width
        if size < PDF_MINIMUM_FONT_SIZE:
            raise ValueError(ERROR_COVERAGE)
        page.add_redact_annot(rectangle, fill=cast(Any, False), cross_out=False)
        inserts.append((line, text, size))
    if inserts:
        page.apply_redactions(
            images=pymupdf.PDF_REDACT_IMAGE_NONE,  # type: ignore[attr-defined]
            graphics=pymupdf.PDF_REDACT_LINE_ART_NONE,  # type: ignore[attr-defined]
            text=pymupdf.PDF_REDACT_TEXT_REMOVE,  # type: ignore[attr-defined]
        )
        for line, text, size in inserts:
            page.insert_text(
                line["origin"],
                text,
                fontsize=size,
                fontname="helv",
                color=pymupdf.sRGB_to_pdf(line["spans"][0]["color"]),
            )


def write_pdf(
    original: Path,
    output: Path,
    replacements: dict[tuple[str, ...], str],
    images: dict[tuple[str, ...], bytes],
) -> None:
    if original.resolve() == output.resolve():
        raise ValueError(ERROR_STRUCTURE)
    with pymupdf.open(original) as document:
        validate_pdf_surfaces(document)
        image_objects = pdf_images(document)
        if set(images) != {
            (PDF_IMAGE_PART, str(number)) for number in range(len(image_objects))
        }:
            raise ValueError(ERROR_COVERAGE)
        for number, (page_number, xref) in enumerate(image_objects):
            document[page_number].replace_image(
                xref, stream=images[(PDF_IMAGE_PART, str(number))]
            )
            document.xref_set_key(xref, "ColorSpace", "/DeviceRGB")
        for page in document.pages():
            _write_page(page, replacements)
        metadata = {
            key: replacements.get(
                (PDF_METADATA_PART, key), (document.metadata or {}).get(key, "") or ""
            )
            for key in PDF_METADATA_FIELDS
        }
        document.set_metadata(metadata)
        _write_auxiliary(document, replacements)
        associated = _associated_relationships(document)
        if associated:
            document.xref_set_key(document.pdf_catalog(), "AF", "null")
        attachments = []
        for number in range(document.embfile_count()):
            info = document.embfile_info(number)
            prefix = f"{PDF_ATTACHMENT_PART}:{number}"
            content = replace_text_fields(
                document.embfile_get(number).decode(TEXT_ENCODING), replacements, prefix
            ).encode(TEXT_ENCODING)
            values = {
                key: replacements.get((prefix, key), str(info.get(key, "")))
                for key in ("name", "filename", "ufilename", "description")
            }
            attachments.append((values, content))
        for name in document.embfile_names():
            document.embfile_del(name)
        references: list[int] = []
        for index, (values, content) in enumerate(attachments):
            first_new_xref = document.xref_length()
            document.embfile_add(
                values["name"],
                content,
                filename=values["filename"],
                ufilename=values["ufilename"],
                desc=values["description"],
            )
            if associated:
                streams = [
                    xref
                    for xref in range(first_new_xref, document.xref_length())
                    if document.xref_is_stream(xref)
                ]
                if len(streams) != 1:
                    raise ValueError(ERROR_COVERAGE)
                xref = document.get_new_xref()
                document.update_object(xref, "<< /Type /Filespec >>")
                for key, field in (
                    ("F", "filename"),
                    ("UF", "ufilename"),
                    ("Desc", "description"),
                ):
                    document.xref_set_key(xref, key, pymupdf.get_pdf_str(values[field]))
                document.xref_set_key(xref, "EF", f"<< /F {streams[0]} 0 R >>")
                document.xref_set_key(xref, "AFRelationship", associated[index])
                references.append(xref)
        if associated:
            document.xref_set_key(
                document.pdf_catalog(),
                "AF",
                "[" + " ".join(f"{xref} 0 R" for xref in references) + "]",
            )
        document.xref_set_key(-1, "ID", "null")
        document.save(
            output,
            garbage=PDF_GARBAGE_LEVEL,
            deflate=True,
            clean=True,
            incremental=False,
        )


def _plain_record(
    values: tuple[str, ...], locations: tuple[tuple[str, ...], ...]
) -> NativeRecord:
    return NativeRecord(
        values=values,
        locations=locations,
        policies=tuple(
            ColumnPolicy(index=index, kind=FIELD_TEXT) for index in range(len(values))
        ),
    )


def _xmp_fields(
    document: pymupdf.Document,
) -> tuple[ElementTree.Element | None, list[tuple[ElementTree.Element, str]]]:
    xml = document.get_xml_metadata()
    if not xml:
        return None, []
    root = fromstring(xml)
    fields: list[tuple[ElementTree.Element, str]] = []
    supported = {
        "adobe:ns:meta/": {"xmpmeta", "xmptk"},
        "http://www.w3.org/1999/02/22-rdf-syntax-ns#": {
            "RDF",
            "Description",
            "Alt",
            "Seq",
            "Bag",
            "li",
            "about",
            "resource",
        },
        "http://purl.org/dc/elements/1.1/": {
            "title",
            "creator",
            "description",
            "subject",
            "rights",
            "publisher",
            "contributor",
            "date",
            "type",
            "format",
            "identifier",
            "source",
            "language",
            "relation",
            "coverage",
        },
        "http://ns.adobe.com/xap/1.0/": {
            "CreatorTool",
            "CreateDate",
            "ModifyDate",
            "MetadataDate",
            "Label",
            "Nickname",
        },
        "http://ns.adobe.com/pdf/1.3/": {"Producer", "Keywords", "PDFVersion"},
        "http://www.w3.org/XML/1998/namespace": {"lang"},
    }
    for element in root.iter():
        for name in (element.tag, *element.attrib):
            if not name.startswith("{"):
                raise ValueError(ERROR_COVERAGE)
            namespace, local = name[1:].split("}", 1)
            if local not in supported.get(namespace, set()):
                raise ValueError(ERROR_COVERAGE)
        if element.text and element.text.strip():
            fields.append((element, "text"))
        if element.tail and element.tail.strip():
            fields.append((element, "tail"))
        for key, value in element.attrib.items():
            if key == "{http://www.w3.org/XML/1998/namespace}lang":
                if not re.fullmatch(r"[A-Za-z]+(?:-[A-Za-z]+)*", value):
                    raise ValueError(ERROR_COVERAGE)
            elif value:
                fields.append((element, key))
    return root, fields


def _auxiliary_records(document: pymupdf.Document) -> list[NativeRecord]:
    records: list[NativeRecord] = []
    _, fields = _xmp_fields(document)
    for index, (element, key) in enumerate(fields):
        value = (
            getattr(element, key) if key in ("text", "tail") else element.attrib[key]
        )
        records.append(_plain_record((value,), ((PDF_XMP_PART, str(index)),)))
    for index, entry in enumerate(document.get_toc(simple=False)):
        if entry[2] < 1 or entry[3].get("kind") != pymupdf.LINK_GOTO:
            raise ValueError(ERROR_COVERAGE)
        records.append(_plain_record((entry[1],), ((PDF_OUTLINE_PART, str(index)),)))
    _associated_relationships(document)
    for page in document.pages():
        for number, annotation in enumerate(page.annots() or ()):
            if annotation.type[0] != pymupdf.PDF_ANNOT_TEXT or annotation.info[  # type: ignore[attr-defined]
                "name"
            ] not in (
                "",
                "Note",
                "Comment",
                "Key",
                "Help",
                "NewParagraph",
                "Paragraph",
                "Insert",
            ):
                raise ValueError(ERROR_COVERAGE)
            keys = ("content", "title", "subject", "creationDate", "modDate", "id")
            records.append(
                _plain_record(
                    tuple(annotation.info[key] for key in keys),
                    tuple(
                        (PDF_ANNOTATION_PART, str(page.number), str(number), key)
                        for key in keys
                    ),
                )
            )
        for number, widget in enumerate(page.widgets() or ()):
            if (
                widget.field_type != pymupdf.PDF_WIDGET_TYPE_TEXT  # type: ignore[attr-defined]
                or widget.field_flags
                or any(
                    getattr(widget, key)
                    for key in (
                        "script",
                        "script_stroke",
                        "script_format",
                        "script_change",
                        "script_calc",
                        "script_blur",
                        "script_focus",
                    )
                )
            ):
                raise ValueError(ERROR_COVERAGE)
            values = (
                widget.field_name or "",
                widget.field_label or "",
                widget.field_value or "",
            )
            if not all(isinstance(value, str) for value in values):
                raise ValueError(ERROR_COVERAGE)
            records.append(
                _plain_record(
                    values,
                    tuple(
                        (PDF_WIDGET_PART, str(page.number), str(number), key)
                        for key in ("name", "label", "value")
                    ),
                )
            )
            for field, key in (("default", "DV"), ("id", "NM")):
                kind, value = document.xref_get_key(widget.xref, key)
                if kind not in ("null", "string"):
                    raise ValueError(ERROR_COVERAGE)
                records.append(
                    _plain_record(
                        (value if kind == "string" else "",),
                        ((PDF_WIDGET_PART, str(page.number), str(number), field),),
                    )
                )
    return records


def _write_auxiliary(
    document: pymupdf.Document, replacements: dict[tuple[str, ...], str]
) -> None:
    root, fields = _xmp_fields(document)
    for index, (element, key) in enumerate(fields):
        value = (
            getattr(element, key) if key in ("text", "tail") else element.attrib[key]
        )
        value = replacements.get((PDF_XMP_PART, str(index)), value)
        if key in ("text", "tail"):
            setattr(element, key, value)
        else:
            element.attrib[key] = value
    if root is not None:
        document.set_xml_metadata(ElementTree.tostring(root, encoding="unicode"))
    outline = document.get_toc(simple=False)
    for index, entry in enumerate(outline):
        entry[1] = replacements.get((PDF_OUTLINE_PART, str(index)), entry[1])
    if outline:
        document.set_toc(outline)
    for page in document.pages():
        for number, annotation in enumerate(page.annots() or ()):
            info = annotation.info
            for key in ("content", "title", "subject", "creationDate", "modDate", "id"):
                info[key] = replacements.get(
                    (PDF_ANNOTATION_PART, str(page.number), str(number), key), info[key]
                )
            annotation.set_info(info)
            if info["id"]:
                document.xref_set_key(
                    annotation.xref, "NM", pymupdf.get_pdf_str(info["id"])
                )
            annotation.update()
        for number, widget in enumerate(page.widgets() or ()):
            prefix = (PDF_WIDGET_PART, str(page.number), str(number))
            widget.field_name = replacements.get((*prefix, "name"), widget.field_name)
            widget.field_label = replacements.get(
                (*prefix, "label"), widget.field_label
            )
            widget.field_value = replacements.get(
                (*prefix, "value"), widget.field_value
            )
            kind, default = document.xref_get_key(widget.xref, "DV")
            if kind == "string":
                document.xref_set_key(
                    widget.xref,
                    "DV",
                    pymupdf.get_pdf_str(
                        replacements.get((*prefix, "default"), default)
                    ),
                )
            widget.update()
            kind, identifier = document.xref_get_key(widget.xref, "NM")
            if kind == "string":
                document.xref_set_key(
                    widget.xref,
                    "NM",
                    pymupdf.get_pdf_str(replacements.get((*prefix, "id"), identifier)),
                )


def _canonical_image(content: bytes) -> bytes:
    with Image.open(BytesIO(content)) as image:
        stream = BytesIO()
        image.convert("RGB").save(stream, format="PNG")
        return stream.getvalue()


def _associated_relationships(document: pymupdf.Document) -> list[str]:
    kind, associated = document.xref_get_key(document.pdf_catalog(), "AF")
    if kind == "null":
        return []
    references = re.findall(r"(\d+) 0 R", associated)
    if kind != "array" or len(references) != document.embfile_count():
        raise ValueError(ERROR_COVERAGE)
    relationships: dict[str, str] = {}
    for reference in references:
        xref = int(reference)
        relationship = document.xref_get_key(xref, "AFRelationship")
        if relationship[0] != "name" or relationship[1] not in (
            "/Data",
            "/Source",
            "/Alternative",
            "/Supplement",
            "/Unspecified",
        ):
            raise ValueError(ERROR_COVERAGE)
        filename = document.xref_get_key(xref, "F")
        if filename[0] != "string" or filename[1] in relationships:
            raise ValueError(ERROR_COVERAGE)
        relationships[filename[1]] = relationship[1]
    names = [
        document.embfile_info(index)["filename"]
        for index in range(document.embfile_count())
    ]
    if set(names) != set(relationships):
        raise ValueError(ERROR_COVERAGE)
    for index, name in enumerate(names):
        reference = next(
            int(item)
            for item in references
            if document.xref_get_key(int(item), "F")[1] == name
        )
        info = document.embfile_info(index)
        for key, field in (("UF", "ufilename"), ("Desc", "description")):
            kind, value = document.xref_get_key(reference, key)
            if kind != "string" or value != info[field]:
                raise ValueError(ERROR_COVERAGE)
        kind, embedded = document.xref_get_key(reference, "EF/F")
        if kind != "xref" or document.xref_stream(
            int(embedded.split()[0])
        ) != document.embfile_get(index):
            raise ValueError(ERROR_COVERAGE)
    return [relationships[name] for name in names]
