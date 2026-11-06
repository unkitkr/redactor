"""Replace package-local relationship labels without changing their target graph."""

from pathlib import PurePosixPath
from xml.etree.ElementTree import Element
from zipfile import ZipFile

from defusedxml.ElementTree import fromstring

from redactor.utils.constants import (
    OFFICE_RELATIONSHIP_ID_TEMPLATE,
    OOXML_OFFICE_RELATIONSHIP_NAMESPACE,
    OOXML_RELATIONSHIP_TAG,
)
from redactor.utils.errors import ERROR_STRUCTURE


def relationship_labels(archive: ZipFile) -> dict[str, dict[str, str]]:
    """Keep each relationship scope separate; labels have no external identity."""
    labels: dict[str, dict[str, str]] = {}
    for part in archive.namelist():
        if not part.endswith(".rels"):
            continue
        root = fromstring(archive.read(part), forbid_dtd=True)
        mapping = {}
        for number, node in enumerate(root, start=1):
            value = node.attrib.get("Id", "")
            if node.tag != OOXML_RELATIONSHIP_TAG or not value or value in mapping:
                raise ValueError(ERROR_STRUCTURE)
            mapping[value] = OFFICE_RELATIONSHIP_ID_TEMPLATE.format(number=number)
        labels[part] = mapping
        location = PurePosixPath(part)
        owner = location.parent.parent / location.name.removesuffix(".rels")
        labels[str(owner)] = mapping
    return labels


def rewrite_relationship_labels(
    root: Element, part: str, labels: dict[str, dict[str, str]]
) -> None:
    mapping = labels.get(part, {})
    for node in root.iter():
        for attribute, value in tuple(node.attrib.items()):
            if (part.endswith(".rels") and attribute == "Id") or (
                attribute.startswith(f"{{{OOXML_OFFICE_RELATIONSHIP_NAMESPACE}}}")
            ):
                replacement = mapping.get(value)
                if replacement is None:
                    raise ValueError(ERROR_STRUCTURE)
                node.set(attribute, replacement)
