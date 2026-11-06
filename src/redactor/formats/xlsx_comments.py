"""Expose each comment as joined rich text and each author as a typed person."""

from xml.etree.ElementTree import Element

from redactor.schemas.native import NativeRecord
from redactor.schemas.redaction import ColumnPolicy
from redactor.utils.constants import (
    FIELD_PERSON_NAME,
    FIELD_TEXT,
    OFFICE_XML_TEXT_MODE,
    XLSX_NAMESPACE,
)


def comment_records(root: Element, part: str) -> tuple[NativeRecord, ...]:
    records = []
    for index, node in enumerate(root.iter()):
        location: tuple[str, ...]
        if node.tag == f"{{{XLSX_NAMESPACE}}}author":
            value = node.text or ""
            kind = FIELD_PERSON_NAME
            location = (part, str(index))
        elif node.tag == f"{{{XLSX_NAMESPACE}}}text":
            value = "".join(
                item.text or "" for item in node.iter(f"{{{XLSX_NAMESPACE}}}t")
            )
            kind = FIELD_TEXT
            location = (part, str(index), OFFICE_XML_TEXT_MODE)
        else:
            continue
        records.append(
            NativeRecord(
                values=(value,),
                policies=(ColumnPolicy(index=0, kind=kind),),
                locations=(location,),
            )
        )
    return tuple(records)
