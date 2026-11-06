"""Validate every carrier in supported legacy comment-shape drawings."""

import re
from xml.etree.ElementTree import Element

from redactor.utils.constants import (
    OFFICE_EXCEL_NAMESPACE,
    OFFICE_VML_NAMESPACE,
    VML_ATTRIBUTE_RULES,
    VML_STYLE_RULES,
)
from redactor.utils.errors import ERROR_COVERAGE, ERROR_STRUCTURE


def check_comment_shapes(root: Element) -> None:
    if root.tag != "xml":
        raise ValueError(ERROR_COVERAGE)
    vocabulary = {tag: dict(attributes) for tag, attributes in VML_ATTRIBUTE_RULES}
    styles = dict(VML_STYLE_RULES)
    identifiers = [node.attrib["id"] for node in root.iter() if "id" in node.attrib]
    if len(set(identifiers)) != len(identifiers):
        raise ValueError(ERROR_STRUCTURE)
    types = {
        node.attrib.get("id")
        for node in root.iter(f"{{{OFFICE_VML_NAMESPACE}}}shapetype")
    }
    for shape in root.iter(f"{{{OFFICE_VML_NAMESPACE}}}shape"):
        if shape.attrib.get("type", "").removeprefix("#") not in types:
            raise ValueError(ERROR_STRUCTURE)
        data = shape.findall(f"{{{OFFICE_EXCEL_NAMESPACE}}}ClientData")
        if len(data) != 1 or any(
            len(data[0].findall(f"{{{OFFICE_EXCEL_NAMESPACE}}}{name}")) != 1
            for name in ("Row", "Column")
        ):
            raise ValueError(ERROR_STRUCTURE)
    for node in root.iter():
        attributes = vocabulary.get(node.tag)
        if attributes is None or not set(node.attrib) <= set(attributes):
            raise ValueError(ERROR_COVERAGE)
        if node.tail and node.tail.strip():
            raise ValueError(ERROR_COVERAGE)
        if node.text and node.text.strip():
            name = node.tag.removeprefix(f"{{{OFFICE_EXCEL_NAMESPACE}}}")
            pattern = (
                r"[0-9]+"
                if name in ("Row", "Column")
                else r"[0-9]+(?:,\s*[0-9]+){7}"
                if name == "Anchor"
                else r"True|False"
                if name in ("AutoFill", "Visible")
                else None
            )
            if pattern is None or re.fullmatch(pattern, node.text.strip()) is None:
                raise ValueError(ERROR_COVERAGE)
        for attribute, value in node.attrib.items():
            if attribute != "style":
                if re.fullmatch(attributes[attribute], value) is None:
                    raise ValueError(ERROR_COVERAGE)
                continue
            for declaration in value.split(";"):
                if not declaration.strip():
                    continue
                name, separator, contents = declaration.partition(":")
                pattern = styles.get(name.strip())
                if (
                    not separator
                    or pattern is None
                    or re.fullmatch(pattern, contents.strip()) is None
                ):
                    raise ValueError(ERROR_COVERAGE)
