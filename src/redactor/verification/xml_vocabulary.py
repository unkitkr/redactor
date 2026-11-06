"""Limit Office XML to supported structural names and their actual attribute roles."""

import re
from xml.etree.ElementTree import Element

from redactor.utils.constants import (
    OOXML_COMMENT_VOCABULARY,
    OOXML_CONTENT_EXTENSIONS,
    OOXML_CONTENT_NAMESPACE,
    OOXML_CONTENT_TYPES,
    OOXML_CORE_NAMESPACE,
    OOXML_CORE_PART,
    OOXML_CORE_VOCABULARY,
    OOXML_DC_TERMS_NAMESPACE,
    OOXML_DRAWING_NAMESPACE,
    OOXML_EXTENDED_NAMESPACE,
    OOXML_EXTENDED_PART,
    OOXML_EXTENDED_VOCABULARY,
    OOXML_PACKAGE_RELATIONSHIPS,
    OOXML_RELATIONSHIP_ID_PATTERN,
    OOXML_RELATIONSHIP_NAMESPACE,
    OOXML_RELATIONSHIP_REFERENCE,
    OOXML_STYLE_VOCABULARY,
    OOXML_SUPPORTED_CONTENT_TYPES,
    OOXML_SUPPORTED_PARTS,
    OOXML_SUPPORTED_RELATIONSHIP_TYPES,
    OOXML_THEME_PART_PATTERN,
    OOXML_THEME_VOCABULARY,
    OOXML_TIMESTAMP_TYPE,
    OOXML_WORKBOOK_RELATIONSHIPS,
    OOXML_WORKBOOK_VOCABULARY,
    OOXML_WORKSHEET_PART_PATTERN,
    OOXML_WORKSHEET_VOCABULARY,
    XLSX_COMMENTS_PATTERN,
    XLSX_NAMESPACE,
    XLSX_SHARED_STRINGS,
    XLSX_SHEET_RELATIONSHIPS_PATTERN,
    XLSX_STYLES,
    XLSX_VML_PATTERN,
    XLSX_WORKBOOK,
    XML_SPACE_ATTRIBUTE,
    XML_TYPE_ATTRIBUTE,
)
from redactor.utils.errors import ERROR_COVERAGE


def supported_xlsx_part(part: str) -> bool:
    return part in OOXML_SUPPORTED_PARTS or any(
        re.fullmatch(pattern, part)
        for pattern in (
            OOXML_WORKSHEET_PART_PATTERN,
            OOXML_THEME_PART_PATTERN,
            XLSX_COMMENTS_PATTERN,
            XLSX_VML_PATTERN,
            XLSX_SHEET_RELATIONSHIPS_PATTERN,
        )
    )


def check_xml_vocabulary(root: Element, part: str) -> None:
    """A familiar value cannot authorize an unknown tag, attribute, or namespace."""
    expected_root, vocabulary = _part_vocabulary(part)
    if root.tag != expected_root:
        raise ValueError(ERROR_COVERAGE)
    for node in root.iter():
        allowed_attributes = vocabulary.get(node.tag)
        if allowed_attributes is None or not set(node.attrib) <= set(
            allowed_attributes
        ):
            raise ValueError(ERROR_COVERAGE)
        for attribute, value in node.attrib.items():
            if attribute == XML_TYPE_ATTRIBUTE and value != OOXML_TIMESTAMP_TYPE:
                raise ValueError(ERROR_COVERAGE)
            if (
                attribute in ("Id", OOXML_RELATIONSHIP_REFERENCE)
                and re.fullmatch(OOXML_RELATIONSHIP_ID_PATTERN, value) is None
            ):
                raise ValueError(ERROR_COVERAGE)
            if attribute == "Type" and value not in OOXML_SUPPORTED_RELATIONSHIP_TYPES:
                raise ValueError(ERROR_COVERAGE)
            if (
                attribute == "ContentType"
                and value not in OOXML_SUPPORTED_CONTENT_TYPES
            ):
                raise ValueError(ERROR_COVERAGE)
            if attribute == "Extension" and value not in OOXML_CONTENT_EXTENSIONS:
                raise ValueError(ERROR_COVERAGE)
            if attribute == "PartName" and (
                not value.startswith("/") or not supported_xlsx_part(value[1:])
            ):
                raise ValueError(ERROR_COVERAGE)


def _qualified_vocabulary(
    namespace: str, entries: tuple[tuple[str, tuple[str, ...]], ...]
) -> dict[str, tuple[str, ...]]:
    return {f"{{{namespace}}}{name}": attributes for name, attributes in entries}


def _part_vocabulary(part: str) -> tuple[str, dict[str, tuple[str, ...]]]:
    entries: tuple[tuple[str, tuple[str, ...]], ...]
    if re.fullmatch(OOXML_WORKSHEET_PART_PATTERN, part):
        namespace, root, entries = (
            XLSX_NAMESPACE,
            "worksheet",
            OOXML_WORKSHEET_VOCABULARY,
        )
    elif re.fullmatch(XLSX_COMMENTS_PATTERN, part):
        namespace, root, entries = XLSX_NAMESPACE, "comments", OOXML_COMMENT_VOCABULARY
    elif part == XLSX_WORKBOOK:
        namespace, root, entries = XLSX_NAMESPACE, "workbook", OOXML_WORKBOOK_VOCABULARY
    elif part == XLSX_STYLES:
        namespace, root, entries = XLSX_NAMESPACE, "styleSheet", OOXML_STYLE_VOCABULARY
    elif part == XLSX_SHARED_STRINGS:
        namespace, root, entries = (
            XLSX_NAMESPACE,
            "sst",
            (
                ("sst", ("count", "uniqueCount")),
                ("si", ()),
                ("t", (XML_SPACE_ATTRIBUTE,)),
            ),
        )
    elif re.fullmatch(OOXML_THEME_PART_PATTERN, part):
        namespace, root, entries = (
            OOXML_DRAWING_NAMESPACE,
            "theme",
            OOXML_THEME_VOCABULARY,
        )
    elif part in (
        OOXML_PACKAGE_RELATIONSHIPS,
        OOXML_WORKBOOK_RELATIONSHIPS,
    ) or re.fullmatch(XLSX_SHEET_RELATIONSHIPS_PATTERN, part):
        namespace, root, entries = (
            OOXML_RELATIONSHIP_NAMESPACE,
            "Relationships",
            (
                ("Relationships", ()),
                ("Relationship", ("Id", "Type", "Target")),
            ),
        )
    elif part == OOXML_CONTENT_TYPES:
        namespace, root, entries = (
            OOXML_CONTENT_NAMESPACE,
            "Types",
            (
                ("Types", ()),
                ("Default", ("Extension", "ContentType")),
                ("Override", ("PartName", "ContentType")),
            ),
        )
    elif part == OOXML_EXTENDED_PART:
        namespace, root = OOXML_EXTENDED_NAMESPACE, "Properties"
        entries = tuple((name, ()) for name in OOXML_EXTENDED_VOCABULARY)
    elif part == OOXML_CORE_PART:
        vocabulary: dict[str, tuple[str, ...]] = {
            f"{{{namespace}}}{name}": (
                (XML_TYPE_ATTRIBUTE,) if namespace == OOXML_DC_TERMS_NAMESPACE else ()
            )
            for namespace, names in OOXML_CORE_VOCABULARY
            for name in names
        }
        return f"{{{OOXML_CORE_NAMESPACE}}}coreProperties", vocabulary
    else:
        raise ValueError(ERROR_COVERAGE)
    return f"{{{namespace}}}{root}", _qualified_vocabulary(namespace, entries)
