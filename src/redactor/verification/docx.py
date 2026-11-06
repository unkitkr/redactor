"""Compare all Word package structure outside the independently exposed surfaces."""

from pathlib import Path
from xml.etree.ElementTree import Element
from zipfile import ZipFile

from redactor.formats.docx import parse_word_xml, word_surfaces
from redactor.utils.constants import DOCX_IMAGE_SUFFIXES, XML_SUFFIXES
from redactor.utils.errors import ERROR_CLINICAL_CHANGED, ERROR_COVERAGE
from redactor.verification.archive import check_saved_archive


def check_docx_structure(original: Path, output: Path) -> None:
    check_saved_archive(output)
    with ZipFile(original) as source, ZipFile(output) as saved:
        if source.namelist() != saved.namelist():
            raise ValueError(ERROR_COVERAGE)
        for part in source.namelist():
            before, after = source.read(part), saved.read(part)
            if part.endswith(XML_SUFFIXES):
                left, right = parse_word_xml(before), parse_word_xml(after)
                _clear_assessed(left, part)
                _clear_assessed(right, part)
                if _structure(left) != _structure(right):
                    raise ValueError(ERROR_CLINICAL_CHANGED)
            elif not part.casefold().endswith(DOCX_IMAGE_SUFFIXES) and before != after:
                raise ValueError(ERROR_COVERAGE)


def _clear_assessed(root: Element, part: str) -> None:
    for _, nodes, attribute in tuple(word_surfaces(root, part)):
        if not attribute:
            for node in nodes:
                node.text = ""
        elif attribute == "text":
            nodes[0].text = ""
        elif attribute == "tail":
            nodes[0].tail = ""
        else:
            nodes[0].set(attribute, "")


def _structure(root: Element) -> tuple[object, ...]:
    return (
        str(root.tag),
        tuple(sorted(root.attrib.items())),
        root.text or "",
        root.tail or "",
        tuple(
            sorted(getattr(root, "nsmap", {}).items(), key=lambda pair: str(pair[0]))
        ),
        tuple(_structure(child) for child in root),
    )
