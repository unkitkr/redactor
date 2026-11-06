"""Independently inventory saved comment text, authors, references, and styles."""

import re
from xml.etree.ElementTree import Element

from redactor.utils.constants import (
    OFFICE_PUBLIC_FONTS,
    OFFICE_XML_TEXT_MODE,
    OOXML_COMMENT_CHILDREN,
    XLSX_NAMESPACE,
    XML_SPACE_ATTRIBUTE,
)
from redactor.utils.errors import ERROR_COVERAGE, ERROR_STRUCTURE


def check_comment_surfaces(
    root: Element, part: str, covered: set[tuple[str, ...]]
) -> None:
    prefix = f"{{{XLSX_NAMESPACE}}}"
    children = {
        prefix + name: {prefix + child for child in allowed}
        for name, allowed in OOXML_COMMENT_CHILDREN
    }
    for node in root.iter():
        if any(child.tag not in children.get(node.tag, set()) for child in node):
            raise ValueError(ERROR_STRUCTURE)
        if node.tag in (prefix + "r", prefix + "rPr"):
            if len({child.tag for child in node}) != len(node):
                raise ValueError(ERROR_STRUCTURE)
        if node.tag == prefix + "text":
            tags = {child.tag for child in node}
            if len(tags) > 1 or (prefix + "t" in tags and len(node) > 1):
                raise ValueError(ERROR_STRUCTURE)
    if tuple(node.tag for node in root) != (prefix + "authors", prefix + "commentList"):
        raise ValueError(ERROR_STRUCTURE)
    authors, comments = root
    if any(node.tag != prefix + "author" or len(node) for node in authors):
        raise ValueError(ERROR_COVERAGE)
    references = set()
    for comment in comments:
        reference = comment.attrib.get("ref", "")
        author = comment.attrib.get("authorId", "")
        if (
            comment.tag != prefix + "comment"
            or re.fullmatch(r"[A-Z]+[1-9][0-9]*", reference) is None
            or reference in references
            or re.fullmatch(r"[0-9]+", author) is None
            or int(author) >= len(authors)
            or len(comment) != 1
            or comment[0].tag != prefix + "text"
        ):
            raise ValueError(ERROR_STRUCTURE)
        references.add(reference)
    text_nodes: set[Element] = set()
    for index, node in enumerate(root.iter()):
        if (part, str(index), OFFICE_XML_TEXT_MODE) in covered:
            if node.tag != prefix + "text":
                raise ValueError(ERROR_COVERAGE)
            text_nodes.update(node.iter(prefix + "t"))
    for index, node in enumerate(root.iter()):
        if node.tail and node.tail.strip():
            raise ValueError(ERROR_COVERAGE)
        if (
            node.text
            and node.text.strip()
            and node not in text_nodes
            and (node.tag != prefix + "author" or (part, str(index)) not in covered)
        ):
            raise ValueError(ERROR_COVERAGE)
        for attribute, value in node.attrib.items():
            if attribute == "ref":
                continue  # Checked with the author and duplicate-coordinate rules.
            if attribute == XML_SPACE_ATTRIBUTE and value == "preserve":
                continue
            if node.tag == prefix + "rFont" and attribute == "val":
                if value in OFFICE_PUBLIC_FONTS:
                    continue
                raise ValueError(ERROR_COVERAGE)
            if node.tag == prefix + "scheme" and value in ("major", "minor", "none"):
                continue
            if node.tag == prefix + "u" and value in ("single", "double", "none"):
                continue
            if attribute == "rgb" and re.fullmatch(r"[0-9A-Fa-f]{8}", value):
                continue
            if re.fullmatch(r"[+-]?[0-9]+(?:\.[0-9]+)?", value):
                continue
            raise ValueError(ERROR_COVERAGE)
