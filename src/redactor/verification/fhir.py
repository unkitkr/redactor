"""Check saved FHIR grammar, reference topology and all unassessed primitives."""

import json
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory

from redactor.formats.fhir import (
    attachment_bytes,
    fhir_narrative_groups,
    fhir_nodes,
    fhir_reference_slots,
    normalize_fhir_birth_bounds,
    parse_fhir_narrative,
    read_fhir_attachment,
)
from redactor.formats.json_syntax import member, member_text, parse_json_text
from redactor.schemas.configuration import ResourceSettings
from redactor.schemas.json import JsonNode
from redactor.schemas.native import NativeDocument
from redactor.utils.constants import FIELD_BIRTH_DATE, FIELD_CLINICAL, UTF8_BOM_ENCODING
from redactor.utils.errors import ERROR_COVERAGE, ERROR_STRUCTURE


def check_fhir_structure(
    original: Path,
    output: Path,
    original_document: NativeDocument,
    resources: ResourceSettings,
) -> None:
    before_text = original.read_text(encoding=UTF8_BOM_ENCODING)
    after_text = output.read_text(encoding=UTF8_BOM_ENCODING)
    json.loads(after_text, parse_float=Decimal, parse_constant=_reject_constant)
    before = parse_json_text(before_text, resources)
    after = parse_json_text(after_text, resources)
    after, generalized = normalize_fhir_birth_bounds(after)
    birth_locations = {
        location
        for record in original_document.records
        for location, policy in zip(record.locations, record.policies, strict=True)
        if policy.kind == FIELD_BIRTH_DATE and policy.supports_date_bounds
    }
    if not set(generalized) <= birth_locations:
        raise ValueError(ERROR_COVERAGE)
    source_nodes, saved_nodes = dict(fhir_nodes(before)), dict(fhir_nodes(after))
    if source_nodes.keys() != saved_nodes.keys():
        raise ValueError(ERROR_STRUCTURE)
    source_refs = fhir_reference_slots(before)
    saved_refs = fhir_reference_slots(after)
    if source_refs.keys() != saved_refs.keys():
        raise ValueError(ERROR_COVERAGE)
    for location, slot in source_refs.items():
        if slot[1:] != saved_refs[location][1:]:
            raise ValueError(ERROR_COVERAGE)
    locations = {
        location
        for record in original_document.records
        for location in record.locations
    }
    protected = {
        location
        for record in original_document.records
        for location, policy in zip(record.locations, record.policies, strict=True)
        if policy.kind == FIELD_CLINICAL
    }
    containers: set[tuple[str, ...]] = set()
    for location, source in source_nodes.items():
        saved = saved_nodes[location]
        if source.kind != saved.kind or len(source.children) != len(saved.children):
            raise ValueError(ERROR_STRUCTURE)
        if source.kind == "object":
            if tuple(child.value for child in source.children[::2]) != tuple(
                child.value for child in saved.children[::2]
            ):
                raise ValueError(ERROR_STRUCTURE)
            if (
                member(source, "contentType") is not None
                and member(source, "data") is not None
            ):
                _check_attachment(source, saved, resources)
                containers.add((*location, "data"))
        elif source.kind == "string" and location[-1] == "div":
            source_xml = tuple(parse_fhir_narrative(source.value).iter())
            saved_xml = tuple(parse_fhir_narrative(saved.value).iter())
            if len(source_xml) != len(saved_xml):
                raise ValueError(ERROR_STRUCTURE)
            for left, right in zip(source_xml, saved_xml, strict=True):
                if (
                    left.tag != right.tag
                    or dict(left.attrib) != dict(right.attrib)
                    or len(left) != len(right)
                ):
                    raise ValueError(ERROR_STRUCTURE)
            source_groups = fhir_narrative_groups(source_xml[0])
            saved_groups = fhir_narrative_groups(saved_xml[0])
            if tuple(index for index, _ in source_groups) != tuple(
                index for index, _ in saved_groups
            ):
                raise ValueError(ERROR_COVERAGE)
            for (index, left_fields), (_, right_fields) in zip(
                source_groups, saved_groups, strict=True
            ):
                path = (*location, "xhtml", str(index))
                if path not in locations and (
                    "".join(
                        getattr(element, attribute) or ""
                        for element, attribute in left_fields
                    )
                    != "".join(
                        getattr(element, attribute) or ""
                        for element, attribute in right_fields
                    )
                ):
                    raise ValueError(ERROR_COVERAGE)
            containers.add(location)
        if (
            not source.children
            and location not in locations
            and location not in containers
        ):
            if source.value != saved.value:
                raise ValueError(ERROR_COVERAGE)
        if location in protected and source.value != saved.value:
            raise ValueError(ERROR_COVERAGE)
        # Numeric spellings, booleans and null values are never string edits.
        if source.kind in ("number", "boolean", "null") and source.value != saved.value:
            raise ValueError(ERROR_COVERAGE)


def _check_attachment(
    source: JsonNode, saved: JsonNode, resources: ResourceSettings
) -> None:
    content_type = member_text(source, "contentType")
    if content_type != member_text(saved, "contentType"):
        raise ValueError(ERROR_STRUCTURE)
    source_bytes, saved_bytes = (
        attachment_bytes(source, resources),
        attachment_bytes(saved, resources),
    )
    document = read_fhir_attachment(source, resources)
    if content_type in ("image/png", "image/jpeg", "image/tiff"):
        return  # The native verifier independently checks every exposed image.
    with TemporaryDirectory(prefix="redactor-fhir-check-") as folder:
        original, output = Path(folder) / "source", Path(folder) / "saved"
        original.write_bytes(source_bytes)
        output.write_bytes(saved_bytes)
        if content_type == "application/pdf":
            from redactor.verification.pdf import check_pdf_structure

            check_pdf_structure(original, output, document)
        elif content_type == "application/json":
            from redactor.verification.json import check_json_surfaces

            check_json_surfaces(original, output, document, resources)
        else:
            raise ValueError(ERROR_COVERAGE)


def _reject_constant(_value: str) -> None:
    raise ValueError(ERROR_STRUCTURE)
