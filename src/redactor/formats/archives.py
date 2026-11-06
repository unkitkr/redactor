"""Bound and validate Office ZIP containers without extracting files."""

import posixpath
import stat
import struct
from pathlib import Path, PurePosixPath
from urllib.parse import unquote, urlsplit
from xml.etree.ElementTree import Element, ParseError
from zipfile import BadZipFile, ZipFile, ZipInfo

from defusedxml import ElementTree
from defusedxml.common import DefusedXmlException

from redactor.schemas.configuration import ResourceSettings
from redactor.schemas.formats import FileFormat
from redactor.utils.constants import (
    DOCX_MAIN_PART,
    DOCX_MAIN_TYPE,
    DOCX_ROOT_TAG,
    FORMAT_DOCX,
    FORMAT_XLSX,
    HASH_CHUNK_BYTES,
    OOXML_CONTENT_TYPES,
    OOXML_EXTERNAL_MODE,
    OOXML_OFFICE_DOCUMENT_RELATIONSHIP,
    OOXML_OVERRIDE_TAG,
    OOXML_PACKAGE_RELATIONSHIPS,
    OOXML_PART_ATTRIBUTE,
    OOXML_RELATIONSHIP_ID,
    OOXML_RELATIONSHIP_MODE,
    OOXML_RELATIONSHIP_TAG,
    OOXML_RELATIONSHIP_TARGET,
    OOXML_RELATIONSHIP_TYPE,
    OOXML_RELATIONSHIPS_TAG,
    OOXML_TYPE_ATTRIBUTE,
    OOXML_TYPES_TAG,
    XLSX_MAIN_PART,
    XLSX_MAIN_TYPE,
    XLSX_ROOT_TAG,
    XML_SUFFIXES,
    ZIP_ENCRYPTED_FLAG,
    ZIP_END_RECORD_BYTES,
    ZIP_END_SIGNATURE,
    ZIP_MAX_COMMENT_BYTES,
    ZIP_MAX_DIRECTORY_BYTES,
    ZIP_MAX_ENTRIES,
)
from redactor.utils.errors import (
    ERROR_CONTAINER,
    ERROR_ENCRYPTED_INPUT,
    ERROR_FORMAT_UNSUPPORTED,
    ERROR_RESOURCE_LIMIT,
)


def inspect_office_archive(path: Path, resources: ResourceSettings) -> FileFormat:
    """Check directory bounds before ZipFile allocates its central-directory list."""
    _check_directory_bounds(path)
    try:
        with ZipFile(path) as archive:
            entries = archive.infolist()
            _check_entries(entries, resources)
            names = {entry.filename for entry in entries}
            if not {OOXML_CONTENT_TYPES, OOXML_PACKAGE_RELATIONSHIPS} <= names:
                raise ValueError(ERROR_FORMAT_UNSUPPORTED)
            content_info = archive.getinfo(OOXML_CONTENT_TYPES)
            if content_info.file_size > resources.max_record_bytes:
                raise ValueError(ERROR_RESOURCE_LIMIT)
            root = ElementTree.fromstring(archive.read(content_info), forbid_dtd=True)
            if root.tag != OOXML_TYPES_TAG:
                raise ValueError(ERROR_CONTAINER)
            main_parts = {
                element.attrib.get(OOXML_PART_ATTRIBUTE, "").lstrip(
                    "/"
                ): element.attrib.get(OOXML_TYPE_ATTRIBUTE)
                for element in root.findall(OOXML_OVERRIDE_TAG)
            }
            if (
                main_parts.get(DOCX_MAIN_PART) == DOCX_MAIN_TYPE
                and main_parts.get(XLSX_MAIN_PART) == XLSX_MAIN_TYPE
            ):
                raise ValueError(ERROR_CONTAINER)
            if main_parts.get(DOCX_MAIN_PART) == DOCX_MAIN_TYPE:
                actual_type: FileFormat = FORMAT_DOCX
                required_part = DOCX_MAIN_PART
            elif main_parts.get(XLSX_MAIN_PART) == XLSX_MAIN_TYPE:
                actual_type = FORMAT_XLSX
                required_part = XLSX_MAIN_PART
            else:
                raise ValueError(ERROR_FORMAT_UNSUPPORTED)
            if required_part not in names:
                raise ValueError(ERROR_CONTAINER)
            package_main_targets: list[str] = []
            for entry in entries:
                if entry.is_dir():
                    continue
                with archive.open(entry) as stream:
                    if entry.filename.endswith(XML_SUFFIXES):
                        stack: list[Element] = []
                        relationship_ids: set[str] = set()
                        for event, element in ElementTree.iterparse(
                            stream, events=("start", "end"), forbid_dtd=True
                        ):
                            if event == "start":
                                if not stack:
                                    _check_root(entry.filename, element.tag)
                                if element.tag == OOXML_RELATIONSHIP_TAG:
                                    _check_relationship(
                                        entry.filename,
                                        element.attrib,
                                        names,
                                        relationship_ids,
                                    )
                                    if (
                                        entry.filename == OOXML_PACKAGE_RELATIONSHIPS
                                        and element.attrib.get(OOXML_RELATIONSHIP_TYPE)
                                        == OOXML_OFFICE_DOCUMENT_RELATIONSHIP
                                    ):
                                        package_main_targets.append(
                                            element.attrib[
                                                OOXML_RELATIONSHIP_TARGET
                                            ].lstrip("/")
                                        )
                                stack.append(element)
                                if len(stack) > resources.max_nesting_depth:
                                    raise ValueError(ERROR_RESOURCE_LIMIT)
                            else:
                                stack.pop()
                                if stack:
                                    stack[-1].remove(element)
                                element.clear()
                    else:
                        while stream.read(HASH_CHUNK_BYTES):
                            pass  # Reading every member also checks its CRC.
            if package_main_targets != [required_part]:
                raise ValueError(ERROR_CONTAINER)
            return actual_type
    except (BadZipFile, ParseError, DefusedXmlException, EOFError, NotImplementedError):
        raise ValueError(ERROR_CONTAINER) from None


def _check_root(name: str, tag: str) -> None:
    expected = None
    if name == DOCX_MAIN_PART:
        expected = DOCX_ROOT_TAG
    elif name == XLSX_MAIN_PART:
        expected = XLSX_ROOT_TAG
    elif name.endswith(XML_SUFFIXES[1]):
        expected = OOXML_RELATIONSHIPS_TAG
    if expected is not None and tag != expected:
        raise ValueError(ERROR_CONTAINER)


def _check_relationship(
    name: str, attributes: dict[str, str], names: set[str], seen: set[str]
) -> None:
    identifier = attributes.get(OOXML_RELATIONSHIP_ID)
    target = attributes.get(OOXML_RELATIONSHIP_TARGET)
    if not identifier or identifier in seen or not target:
        raise ValueError(ERROR_CONTAINER)
    seen.add(identifier)
    if len(seen) > ZIP_MAX_ENTRIES:
        raise ValueError(ERROR_RESOURCE_LIMIT)
    if attributes.get(OOXML_RELATIONSHIP_MODE) == OOXML_EXTERNAL_MODE:
        return  # External links are data for analysis; inspection never fetches them.
    relative_target = unquote(urlsplit(target).path)
    base = PurePosixPath(name).parent.parent.as_posix()
    resolved = posixpath.normpath(posixpath.join(base, relative_target)).lstrip("/")
    if resolved not in names:
        raise ValueError(ERROR_CONTAINER)


def _check_directory_bounds(path: Path) -> None:
    with path.open("rb") as stream:
        size = path.stat().st_size
        tail_size = min(size, ZIP_END_RECORD_BYTES + ZIP_MAX_COMMENT_BYTES)
        stream.seek(size - tail_size)
        tail = stream.read(tail_size)
    position = tail.rfind(ZIP_END_SIGNATURE)
    if position < 0 or len(tail) - position < ZIP_END_RECORD_BYTES:
        raise ValueError(ERROR_CONTAINER)
    _, disk, directory_disk, disk_entries, entries, length, offset, comment = (
        struct.unpack_from("<4s4H2IH", tail, position)
    )
    if disk or directory_disk or disk_entries != entries:
        raise ValueError(ERROR_FORMAT_UNSUPPORTED)
    if entries > ZIP_MAX_ENTRIES or length > ZIP_MAX_DIRECTORY_BYTES:
        raise ValueError(ERROR_RESOURCE_LIMIT)
    if (
        position + ZIP_END_RECORD_BYTES + comment != len(tail)
        or offset + length > size - tail_size + position
    ):
        raise ValueError(ERROR_CONTAINER)


def _check_entries(entries: list[ZipInfo], resources: ResourceSettings) -> None:
    if len(entries) > ZIP_MAX_ENTRIES:
        raise ValueError(ERROR_RESOURCE_LIMIT)
    names: set[str] = set()
    total_bytes = 0
    for entry in entries:
        name = PurePosixPath(entry.filename)
        if (
            entry.filename in names
            or name.is_absolute()
            or ".." in name.parts
            or "\\" in entry.filename
            or "\x00" in entry.orig_filename
            or stat.S_ISLNK(entry.external_attr >> 16)
        ):
            raise ValueError(ERROR_CONTAINER)
        if entry.flag_bits & ZIP_ENCRYPTED_FLAG:
            raise ValueError(ERROR_ENCRYPTED_INPUT)
        names.add(entry.filename)
        total_bytes += entry.file_size
        if (
            entry.file_size > resources.max_native_file_bytes
            or total_bytes > resources.max_archive_bytes
        ):
            raise ValueError(ERROR_RESOURCE_LIMIT)
