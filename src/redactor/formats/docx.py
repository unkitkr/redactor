"""Rewrite Word XML runs, metadata and embedded images in a fresh archive."""

import posixpath
import re
from collections.abc import Iterator
from pathlib import Path
from typing import cast
from urllib.parse import unquote, urlsplit
from xml.etree.ElementTree import Element
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

from lxml import etree

from redactor.formats.archives import inspect_office_archive
from redactor.formats.tabular_fields import column_policies
from redactor.formats.text import replace_text_fields, text_record
from redactor.formats.xml_text import replace_text_nodes
from redactor.identity.tabular import row_evidence
from redactor.policy.identifiers import canonical_uuid
from redactor.policy.name_matching import compatible_name_spelling
from redactor.schemas.configuration import ResourceSettings
from redactor.schemas.native import NativeDocument, NativeImage, NativeRecord
from redactor.schemas.redaction import ColumnPolicy, FieldKind, RowEvidence
from redactor.utils.constants import (
    DOCX_BUILTIN_STYLE_PATTERN,
    DOCX_CUSTOM_XML_ITEM_ID_NAMESPACE,
    DOCX_DATA_BINDING_TAG,
    DOCX_DATASTORE_ITEM_ID_ATTRIBUTE,
    DOCX_DATASTORE_ITEM_TAG,
    DOCX_FORMAT_ENUMS,
    DOCX_HEX_ELEMENTS,
    DOCX_IMAGE_SUFFIXES,
    DOCX_INSTRUCTION_TAG,
    DOCX_NUMERIC_ATTRIBUTES,
    DOCX_NUMERIC_ELEMENTS,
    DOCX_PACKAGE_PART_PATTERN,
    DOCX_PARAGRAPH_TAG,
    DOCX_PUBLIC_URIS,
    DOCX_SCHEMA_LABELS,
    DOCX_SCHEMA_NAMESPACES,
    DOCX_SCHEMA_PREFIXES,
    DOCX_STORE_ITEM_ID_ATTRIBUTE,
    DOCX_STYLE_ELEMENTS,
    DOCX_TEXT_TAGS,
    FIELD_DATE,
    FIELD_IDENTIFIER,
    FIELD_PATIENT_NAME,
    FIELD_PERSON_NAME,
    FIELD_TEXT,
    FIELD_WEB,
    FORMAT_DOCX,
    NATIVE_IMAGE_LOCATION,
    OFFICE_PUBLIC_FONTS,
    OFFICE_STRUCTURAL_VALUES,
    OOXML_CONTENT_TYPES,
    OOXML_NAMESPACE_PREFIX_PATTERN,
    OOXML_OVERRIDE_TAG,
    OOXML_PACKAGE_RELATIONSHIPS,
    OOXML_RELATIONSHIP_NAMESPACE,
    OOXML_RELATIONSHIP_TAG,
    OOXML_SUPPORTED_RELATIONSHIP_TYPES,
    TEXT_ENCODING,
    XML_SUFFIXES,
    ZIP_FIXED_TIMESTAMP,
)
from redactor.utils.errors import ERROR_COVERAGE, ERROR_STRUCTURE


def parse_word_xml(content: bytes) -> Element:
    parser = etree.XMLParser(resolve_entities=False, no_network=True, load_dtd=False)
    root = etree.fromstring(content, parser)
    if (
        root.getroottree().docinfo.doctype
        or root.getprevious() is not None
        or root.getnext() is not None
    ):
        raise ValueError(ERROR_COVERAGE)
    return cast(Element, root)


def custom_xml_binding_targets(
    archive: ZipFile,
) -> dict[tuple[str, str], tuple[str, str]]:
    """Resolve each content-control binding to a unique custom XML definition.

    GUID spelling is case-insensitive and may use braces. Missing definitions
    and duplicate IDs cannot establish a safe binding graph.
    """
    definitions: dict[str, tuple[str, str]] = {}
    references: dict[tuple[str, str], str] = {}
    for part in archive.namelist():
        if not part.endswith(XML_SUFFIXES):
            continue
        for index, element in enumerate(parse_word_xml(archive.read(part)).iter()):
            location = part, str(index)
            if element.tag == DOCX_DATASTORE_ITEM_TAG:
                value = canonical_uuid(
                    element.attrib.get(DOCX_DATASTORE_ITEM_ID_ATTRIBUTE, "")
                )
                if value in definitions:
                    raise ValueError(ERROR_COVERAGE)
                definitions[value] = location
            elif element.tag == DOCX_DATA_BINDING_TAG:
                references[location] = canonical_uuid(
                    element.attrib.get(DOCX_STORE_ITEM_ID_ATTRIBUTE, "")
                )
    if any(value not in definitions for value in references.values()):
        raise ValueError(ERROR_COVERAGE)
    return {location: definitions[value] for location, value in references.items()}


def optional_thumbnails(archive: ZipFile) -> set[str]:
    """Remove only package previews that have no non-preview consumer."""
    candidates: set[str] = set()
    referenced: set[str] = set()
    for part in archive.namelist():
        if not part.endswith(".rels"):
            continue
        root = parse_word_xml(archive.read(part))
        for relation in root:
            target = relation.attrib.get("Target", "")
            thumbnail = (
                part == OOXML_PACKAGE_RELATIONSHIPS
                and relation.attrib.get("Type")
                == OOXML_RELATIONSHIP_NAMESPACE + "/metadata/thumbnail"
            )
            if relation.attrib.get("TargetMode") == "External":
                if thumbnail:
                    raise ValueError(ERROR_COVERAGE)
                continue
            base = posixpath.dirname(posixpath.dirname(part))
            resolved = posixpath.normpath(
                posixpath.join(base, unquote(urlsplit(target).path))
            ).lstrip("/")
            if thumbnail:
                if not (
                    resolved.startswith("docProps/thumbnail.")
                    and resolved.endswith(DOCX_IMAGE_SUFFIXES)
                    and resolved in archive.namelist()
                ):
                    raise ValueError(ERROR_COVERAGE)
                candidates.add(resolved)
            else:
                referenced.add(resolved)
    return candidates - referenced


def remove_thumbnail_references(
    root: Element, part: str, thumbnails: set[str], remaining: set[str]
) -> None:
    if not thumbnails:
        return
    if part == OOXML_PACKAGE_RELATIONSHIPS:
        for relation in tuple(root):
            if (
                relation.attrib.get("Type")
                == OOXML_RELATIONSHIP_NAMESPACE + "/metadata/thumbnail"
                and posixpath.normpath(
                    unquote(urlsplit(relation.attrib.get("Target", "")).path)
                ).lstrip("/")
                in thumbnails
            ):
                root.remove(relation)
    elif part == OOXML_CONTENT_TYPES:
        extensions = {name.rsplit(".", 1)[-1] for name in thumbnails}
        used = {name.rsplit(".", 1)[-1] for name in remaining}
        for declaration in tuple(root):
            if (
                declaration.tag == OOXML_OVERRIDE_TAG
                and declaration.attrib.get("PartName", "").lstrip("/") in thumbnails
                or declaration.attrib.get("Extension") in extensions - used
            ):
                root.remove(declaration)


def _technical_attribute(element: Element, attribute: str, value: str) -> bool:
    """Validate typed Office formatting; arbitrary strings remain assessable."""
    tag = str(element.tag)
    namespace, _, local = tag.removeprefix("{").partition("}")
    name = attribute.rsplit("}", 1)[-1]
    if namespace not in DOCX_SCHEMA_NAMESPACES:
        return False
    if (
        attribute.startswith("{")
        and attribute[1:].split("}")[0] not in DOCX_SCHEMA_NAMESPACES
    ):
        return False
    if name == "space":
        return value in ("preserve", "default") or bool(re.fullmatch(r"[0-9]+", value))
    if name in ("Ignorable", "Requires"):
        prefixes = getattr(element, "nsmap", {})
        return all(
            prefixes.get(prefix) in DOCX_SCHEMA_NAMESPACES for prefix in value.split()
        )
    if name in ("Id", "embed", "link") or (
        name == "id" and "relationships" in attribute
    ):
        return bool(re.fullmatch(r"rId[1-9][0-9]*", value))
    if name == "TargetMode":
        return element.tag == OOXML_RELATIONSHIP_TAG and value == "External"
    if name in ("Type", "ContentType"):
        if value in OOXML_SUPPORTED_RELATIONSHIP_TYPES or value in (
            "http://schemas.openxmlformats.org/package/2006/relationships/metadata/thumbnail",
            "http://schemas.microsoft.com/office/2007/relationships/stylesWithEffects",
            "application/vnd.ms-word.stylesWithEffects+xml",
        ):
            return True
        return bool(
            re.fullmatch(
                r"http://schemas\.openxmlformats\.org/(?:officeDocument|package)/2006/"
                r"relationships/(?:officeDocument|extended-properties|styles|theme|"
                r"settings|webSettings|fontTable|numbering|comments|footnotes|endnotes|"
                r"header|footer|image|hyperlink|customXml|customXmlProps)"
                r"|application/vnd\.openxmlformats-officedocument\."
                r"(?:wordprocessingml\.(?:document\.main|styles|numbering|settings|"
                r"webSettings|fontTable|comments|header|footer|footnotes|endnotes)|"
                r"extended-properties|custom-properties|theme|customXmlProperties)\+xml"
                r"|application/vnd\.openxmlformats-package\.(?:relationships|core-properties)\+xml"
                r"|application/xml|image/(?:png|jpeg|tiff)",
                value,
            )
        )
    if name == "Extension":
        return value in ("xml", "rels", "png", "jpg", "jpeg", "tif", "tiff")
    if name == "PartName":
        return bool(re.fullmatch(DOCX_PACKAGE_PART_PATTERN, value.lstrip("/")))
    if name == "type" and value == "dcterms:W3CDTF":
        return True
    if name == "uri" and value in DOCX_PUBLIC_URIS:
        return True
    if name in DOCX_NUMERIC_ATTRIBUTES or (
        name == "val" and local in DOCX_NUMERIC_ELEMENTS
    ):
        if re.fullmatch(r"-?[0-9]+", value):
            return True
    if name in ("color", "fill", "lastClr") or (
        name == "val" and local in ("color", "srgbClr")
    ):
        return bool(re.fullmatch(r"[0-9A-Fa-f]{6}|auto", value))
    if name in ("themeFillTint", "themeFillShade", "themeTint", "themeShade"):
        return bool(re.fullmatch(r"[0-9A-Fa-f]{2}", value))
    if (name == "val" and local in DOCX_HEX_ELEMENTS) or name.startswith(
        ("usb", "csb")
    ):
        return bool(re.fullmatch(r"[0-9A-Fa-f]{2,20}", value))
    if name in ("ascii", "hAnsi", "eastAsia", "cs", "typeface") or (
        local in ("font", "mathFont") and name in ("name", "val")
    ):
        if value in OFFICE_PUBLIC_FONTS:
            return True
    if (
        name == "val"
        and local in DOCX_STYLE_ELEMENTS
        or name == "styleId"
        and local == "style"
        or name == "name"
        and local == "lsdException"
    ):
        return bool(re.fullmatch(DOCX_BUILTIN_STYLE_PATTERN, value))
    if local in ("lang", "themeFontLang") and name in ("val", "eastAsia", "bidi"):
        return bool(re.fullmatch(r"[a-z]{2,3}(?:-[A-Za-z0-9]{2,8})*", value))
    if name == "script":
        return bool(re.fullmatch(r"[A-Z][a-z]{3}", value))
    if name == "val" and local == "lvlText":
        return bool(re.fullmatch(r"(?:%[1-9]|[.()\- \u2022\uf0b7])+", value))
    if local == "tblLook" and name == "val":
        return bool(re.fullmatch(r"[0-9A-Fa-f]{4}", value))
    if local == "tblLook" and name in (
        "firstColumn",
        "firstRow",
        "lastColumn",
        "lastRow",
        "noHBand",
        "noVBand",
    ):
        return value in ("0", "1", "true", "false")
    if name == "val" and local in ("family", "pitch"):
        return value in (
            "auto",
            "decorative",
            "modern",
            "roman",
            "script",
            "swiss",
            "default",
            "fixed",
            "variable",
        )
    if local == "clrSchemeMapping":
        return bool(
            re.fullmatch(
                r"accent[1-6]|light[12]|dark[12]|hyperlink|followedHyperlink", value
            )
        )
    if local == "compatSetting" and name == "val":
        return bool(re.fullmatch(r"[0-9]+", value))
    if value in OFFICE_STRUCTURAL_VALUES and local not in ("docPr", "cNvPr"):
        return True
    return any(
        name == key and re.fullmatch(pattern, value)
        for key, pattern in DOCX_FORMAT_ENUMS
    )


def _paragraph_nodes(element: Element) -> Iterator[Element]:
    for child in element:
        if child.tag == DOCX_PARAGRAPH_TAG:
            continue
        if child.tag in DOCX_TEXT_TAGS:
            yield child
        yield from _paragraph_nodes(child)


def word_surfaces(
    root: Element, part: str
) -> Iterator[tuple[NativeRecord, tuple[Element, ...], str]]:
    """Stable element positions also cover revisions, comments and custom XML."""
    grouped: set[Element] = set()
    for index, element in enumerate(root.iter()):
        location = (part, str(index))
        if element.tag == DOCX_INSTRUCTION_TAG and (element.text or "").strip():
            raise ValueError(ERROR_COVERAGE)
        if element.tag == DOCX_PARAGRAPH_TAG:
            # Text boxes can nest paragraphs inside a paragraph's drawing run.
            paragraph_nodes = tuple(_paragraph_nodes(element))
            for text_tag in DOCX_TEXT_TAGS:
                nodes = tuple(node for node in paragraph_nodes if node.tag == text_tag)
                if not nodes:
                    continue
                grouped.update(nodes)
                record = text_record("".join(node.text or "" for node in nodes))
                yield (
                    record.model_copy(
                        update={
                            "locations": tuple(
                                (*location, text_tag, *value)
                                for value in record.locations
                            )
                        }
                    ),
                    nodes,
                    "",
                )
        elif element not in grouped and (element.text or "").strip():
            name = str(element.tag).rsplit("}", 1)[-1]
            policy = column_policies((name,))[0]
            if name.casefold() == "name" and "customXml/" in part:
                policy = ColumnPolicy(index=0, kind=FIELD_PATIENT_NAME)
            elif name.casefold() in ("creator", "lastmodifiedby", "manager"):
                policy = ColumnPolicy(index=0, kind=FIELD_PERSON_NAME)
            elif name.casefold() in ("created", "modified"):
                policy = ColumnPolicy(index=0, kind=FIELD_DATE)
            yield (
                NativeRecord(
                    values=(element.text or "",),
                    policies=(policy,),
                    locations=((*location, "text"),),
                ),
                (element,),
                "text",
            )
        if (element.tail or "").strip():
            yield (
                NativeRecord(
                    values=(element.tail or "",),
                    policies=(ColumnPolicy(index=0, kind=FIELD_TEXT),),
                    locations=((*location, "tail"),),
                ),
                (element,),
                "tail",
            )
        for attribute, value in sorted(element.attrib.items()):
            name = attribute.rsplit("}", 1)[-1]
            if not value.strip() or _technical_attribute(element, attribute, value):
                continue
            kind: FieldKind = FIELD_TEXT
            namespace = ""
            if (element.tag, attribute) in (
                (DOCX_DATASTORE_ITEM_TAG, DOCX_DATASTORE_ITEM_ID_ATTRIBUTE),
                (DOCX_DATA_BINDING_TAG, DOCX_STORE_ITEM_ID_ATTRIBUTE),
            ):
                canonical_uuid(value)
                kind, namespace = FIELD_IDENTIFIER, DOCX_CUSTOM_XML_ITEM_ID_NAMESPACE
            elif element.tag == OOXML_RELATIONSHIP_TAG and name == "Target":
                if element.attrib.get("TargetMode") != "External":
                    # Canonical part names contain format roles and counters only.
                    if re.fullmatch(
                        r"(?:\.\./)*", value.rsplit("/", 1)[0] + "/"
                    ) or re.fullmatch(DOCX_PACKAGE_PART_PATTERN, value.lstrip("/")):
                        continue
                    if re.fullmatch(
                        r"(?:\.\./)*(?:[A-Za-z]+/)*[A-Za-z]+[0-9]*\.(?:xml|rels|png|jpe?g|tiff?)",
                        value,
                    ):
                        continue
                else:
                    kind = FIELD_WEB
            elif name.casefold() in ("author", "initials"):
                kind = FIELD_PERSON_NAME
            elif name.casefold() in ("date", "created", "modified"):
                kind = FIELD_DATE
            elif str(element.tag).endswith("}docId") and name == "val":
                kind, namespace = FIELD_IDENTIFIER, "document"
            elif (
                str(element.tag).rsplit("}", 1)[-1] in ("docPr", "cNvPr")
                and name == "name"
            ):
                kind, namespace = FIELD_IDENTIFIER, "document-label"
            yield (
                NativeRecord(
                    values=(value,),
                    policies=(ColumnPolicy(index=0, kind=kind, namespace=namespace),),
                    locations=((*location, "attribute", attribute),),
                ),
                (element,),
                attribute,
            )


def _context_records(records: list[NativeRecord], part: str) -> list[NativeRecord]:
    """Only a single nonconflicting declared subject supplies document context."""
    values = tuple(value for record in records for value in record.values)
    policies = tuple(
        policy.model_copy(update={"index": index})
        for index, policy in enumerate(
            policy for record in records for policy in record.policies
        )
    )
    evidence = row_evidence(values, policies, part, 0)
    if evidence.patient is None and evidence.provider is None:
        return records
    return [
        record.model_copy(update={"evidence": evidence, "context_scope": part})
        for record in records
    ]


def _schema_record(root: Element, part: str) -> NativeRecord | None:
    """Assess XML names and custom namespace labels without rewriting vocabulary."""
    labels: set[str] = set()
    for element in root.iter():
        if isinstance(element.tag, str):
            namespace = (
                element.tag[1:].split("}")[0] if element.tag.startswith("{") else ""
            )
            name = element.tag.rsplit("}", 1)[-1]
            if (
                namespace not in DOCX_SCHEMA_NAMESPACES
                or name not in DOCX_SCHEMA_LABELS
            ):
                labels.add(name)
        else:
            target = getattr(element, "target", None)
            if target:
                labels.add(target)
        labels.update(
            name.rsplit("}", 1)[-1]
            for name in element.attrib
            if name.rsplit("}", 1)[-1] not in DOCX_SCHEMA_LABELS
        )
        for prefix, namespace in getattr(element, "nsmap", {}).items():
            if (
                prefix
                and prefix not in DOCX_SCHEMA_PREFIXES
                and re.fullmatch(OOXML_NAMESPACE_PREFIX_PATTERN, prefix) is None
            ):
                labels.add(prefix)
            if namespace not in DOCX_SCHEMA_NAMESPACES:
                labels.add(namespace)
    if not labels:
        return None
    return NativeRecord(
        values=("\n".join(sorted(labels)),),
        policies=(ColumnPolicy(index=0, kind=FIELD_TEXT),),
        locations=((part, "schema"),),
    )


def _document_context(
    records: list[NativeRecord], subject_parts: set[str]
) -> list[NativeRecord]:
    anchors = {
        record.evidence.patient
        for record in records
        if record.context_scope in subject_parts
        and record.evidence
        and record.evidence.patient
        and record.evidence.patient.identifier
        and record.evidence.patient.birth_date
    }
    if len(anchors) != 1:
        return records
    anchor = next(iter(anchors))
    result: list[NativeRecord] = []
    for record in records:
        evidence = record.evidence
        if (
            record.context_scope == "word/document.xml"
            and evidence
            and evidence.patient
            and anchor.name
            and compatible_name_spelling(evidence.patient.name, anchor.name)
            and (
                not evidence.patient.identifier
                or evidence.patient.identifier == anchor.identifier
            )
            and (
                not evidence.patient.birth_date
                or evidence.patient.birth_date == anchor.birth_date
            )
        ):
            references = tuple(
                value
                for value in (anchor.reference_date, evidence.patient.reference_date)
                if value is not None
            )
            patient = anchor.model_copy(
                update={
                    "reference_date": max(references) if references else None,
                    "explicit_older_age": anchor.explicit_older_age
                    or evidence.patient.explicit_older_age,
                }
            )
            record = record.model_copy(
                update={
                    "evidence": RowEvidence(patient=patient, provider=evidence.provider)
                }
            )
        result.append(record)
    return result


def read_docx(
    path: Path, resources: ResourceSettings, *, extract_evidence: bool = True
) -> NativeDocument:
    if inspect_office_archive(path, resources) != FORMAT_DOCX:
        raise ValueError(ERROR_STRUCTURE)
    records: list[NativeRecord] = []
    images: list[NativeImage] = []
    subject_parts: set[str] = set()
    with ZipFile(path) as archive:
        custom_xml_binding_targets(archive)
        thumbnails = optional_thumbnails(archive)
        remaining = set(archive.namelist()) - thumbnails
        for part in archive.namelist():
            if part.endswith("/") or part in thumbnails:
                continue
            if not re.fullmatch(DOCX_PACKAGE_PART_PATTERN, part):
                raise ValueError(ERROR_COVERAGE)
            content = archive.read(part)
            if part.endswith(XML_SUFFIXES):
                root = parse_word_xml(content)
                remove_thumbnail_references(root, part, thumbnails, remaining)
                subject = str(root.tag).rsplit("}", 1)[-1]
                if part.startswith("customXml/") and re.sub(
                    r"[_ -]", "", subject.casefold()
                ) in ("patient", "patientcontext", "patientrecord", "demographics"):
                    subject_parts.add(part)
                part_records = [record for record, _, _ in word_surfaces(root, part)]
                if extract_evidence and (
                    part == "word/document.xml" or part.startswith("customXml/item")
                ):
                    part_records = _context_records(part_records, part)
                records.extend(part_records)
                schema_record = _schema_record(root, part)
                if schema_record is not None:
                    records.append(schema_record)
            elif part.casefold().endswith(DOCX_IMAGE_SUFFIXES):
                images.append(
                    NativeImage(location=(NATIVE_IMAGE_LOCATION, part), content=content)
                )
            else:
                raise ValueError(ERROR_COVERAGE)
    if extract_evidence:
        records = _document_context(records, subject_parts)
    return NativeDocument(records=tuple(records), images=tuple(images))


def write_docx(
    original: Path,
    output: Path,
    replacements: dict[tuple[str, ...], str],
    images: dict[tuple[str, ...], bytes],
) -> None:
    used: set[tuple[str, ...]] = set()
    used_images: set[tuple[str, ...]] = set()
    with (
        ZipFile(original) as source,
        ZipFile(output, "w", compression=ZIP_DEFLATED) as target,
    ):
        thumbnails = optional_thumbnails(source)
        remaining = set(source.namelist()) - thumbnails
        for part in source.namelist():
            if part in thumbnails:
                continue
            content = source.read(part)
            if part.endswith(XML_SUFFIXES):
                root = parse_word_xml(content)
                remove_thumbnail_references(root, part, thumbnails, remaining)
                # Freeze locations before a changed scalar can alter classification.
                for record, nodes, attribute in tuple(word_surfaces(root, part)):
                    changes = {
                        location: replacements[location]
                        for location in record.locations
                        if location in replacements
                    }
                    used.update(changes)
                    if not changes:
                        continue
                    if not attribute:
                        local = {
                            location[3:]: value for location, value in changes.items()
                        }
                        value = replace_text_fields(
                            "".join(node.text or "" for node in nodes), local
                        )
                        replace_text_nodes(nodes, value)
                    else:
                        value = changes[record.locations[0]]
                        if attribute.rsplit("}", 1)[-1] in (
                            "Id",
                            "Type",
                            "ContentType",
                            "PartName",
                            "Extension",
                            "embed",
                            "link",
                            "Ignorable",
                            "Requires",
                        ):
                            raise ValueError(ERROR_COVERAGE)
                        if attribute == "text":
                            nodes[0].text = value
                        elif attribute == "tail":
                            nodes[0].tail = value
                        else:
                            nodes[0].set(attribute, value)
                content = cast(
                    bytes,
                    etree.tostring(root, encoding=TEXT_ENCODING, xml_declaration=True),
                )
            elif (NATIVE_IMAGE_LOCATION, part) in images:
                key = (NATIVE_IMAGE_LOCATION, part)
                content = images[key]
                used_images.add(key)
            target.writestr(
                ZipInfo(part, date_time=ZIP_FIXED_TIMESTAMP),
                content,
                compress_type=ZIP_DEFLATED,
            )
    if used != set(replacements) or used_images != set(images):
        raise ValueError(ERROR_COVERAGE)
