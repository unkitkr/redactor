"""Parse all XML carriers, retaining comments and processing instructions."""

import re
from io import BytesIO
from typing import cast
from xml.etree.ElementTree import Element

from defusedxml.ElementTree import iterparse

from redactor.utils.constants import (
    OOXML_NAMESPACE_PREFIX_PATTERN,
    OOXML_VERIFIED_NAMESPACES,
)
from redactor.utils.errors import ERROR_COVERAGE


def read_verified_xml(payload: bytes) -> Element:
    parser = iterparse(
        BytesIO(payload), events=("end", "comment", "pi", "start-ns"), forbid_dtd=True
    )
    root: Element | None = None
    for event, element in parser:
        if event == "start-ns":
            prefix, namespace = cast(tuple[str, str], element)
            if namespace not in OOXML_VERIFIED_NAMESPACES or not re.fullmatch(
                OOXML_NAMESPACE_PREFIX_PATTERN, prefix
            ):
                raise ValueError(ERROR_COVERAGE)
            continue
        # Include carriers outside the root, which ordinary tree parsing drops.
        if event in ("comment", "pi"):
            raise ValueError(ERROR_COVERAGE)
        root = cast(Element, element)
    if root is None:
        raise ValueError(ERROR_COVERAGE)
    return root
