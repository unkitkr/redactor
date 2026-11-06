"""Expose bounded FHIR resources without flattening references or clinical values."""

import base64
import binascii
import json
import re
from collections.abc import Iterator
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Literal, cast
from xml.etree.ElementTree import Element

from lxml import etree
from PIL import Image, UnidentifiedImageError

from redactor.formats.json_context import human_name
from redactor.formats.json_syntax import (
    member,
    member_text,
    object_members,
    parse_json_text,
)
from redactor.formats.tabular_fields import validate_clinical_field
from redactor.formats.xml_text import replace_text_nodes
from redactor.identity.tabular import canonical_record_identifier
from redactor.policy.dates import parse_date
from redactor.schemas.configuration import ResourceSettings
from redactor.schemas.identity import IdentityEvidence
from redactor.schemas.json import JsonNode
from redactor.schemas.native import NativeDocument, NativeImage, NativeRecord
from redactor.schemas.redaction import ColumnPolicy, RowEvidence
from redactor.utils.constants import (
    AGE_GROUP_LABEL,
    BIRTH_BOUND_TEMPLATE,
    FHIR_AGE_BAND_URL,
    FHIR_BIRTH_BOUND_URL,
    FHIR_DATA_ABSENT_REASON_URL,
    FIELD_ADDRESS,
    FIELD_BIRTH_DATE,
    FIELD_CLINICAL,
    FIELD_DATE,
    FIELD_EMAIL,
    FIELD_IDENTIFIER,
    FIELD_LOCATION,
    FIELD_PATIENT_ID,
    FIELD_PATIENT_NAME,
    FIELD_PERSON_NAME,
    FIELD_PHONE,
    FIELD_PROVIDER_ID,
    FIELD_PROVIDER_NAME,
    FIELD_RELATIVE_NAME,
    FIELD_SSN,
    FIELD_TEXT,
    FIELD_ZIP,
    FORMAT_FHIR,
    LAB_DESCRIPTION_NAMESPACE,
    MEDICATION_DISPLAY_NAMESPACE,
    MRN_NAMESPACE,
    NPI_NAMESPACE,
    PIXEL_JPEG_FORMAT,
    PIXEL_PNG_FORMAT,
    PIXEL_TIFF_FORMAT,
    SSN_NAMESPACE,
    TEXT_ENCODING,
    UTF8_BOM_ENCODING,
)
from redactor.utils.errors import ERROR_COVERAGE, ERROR_RESOURCE_LIMIT, ERROR_STRUCTURE


def fhir_birth_bound_metadata(value: str) -> dict[str, object]:
    """Suppress exact DOB, recording an inclusive upper-bound year and 90+ band.

    Custom extension URLs are local canonical identifiers. valueDate retains only
    year precision; its meaning is an inclusive upper bound, never a known DOB.
    The standard masked reason marks the omitted birthDate primitive itself.
    """
    match = re.fullmatch(BIRTH_BOUND_TEMPLATE.format(year=r"(?P<year>[0-9]{4})"), value)
    if match is None or int(match["year"]) < 1:
        raise ValueError(ERROR_COVERAGE)
    return {
        "extension": [
            {"url": FHIR_DATA_ABSENT_REASON_URL, "valueCode": "masked"},
            {"url": FHIR_AGE_BAND_URL, "valueString": AGE_GROUP_LABEL},
            {"url": FHIR_BIRTH_BOUND_URL, "valueDate": match["year"]},
        ]
    }


def normalize_fhir_birth_bounds(
    root: JsonNode,
) -> tuple[JsonNode, tuple[tuple[str, ...], ...]]:
    """Expose only the exact saved masking representation as a logical DOB slot.

    This normalization permits one structural substitution. The native verifier
    still compares its logical value to the expected identity-bound date edit.
    """
    transformed: list[tuple[str, ...]] = []

    def visit(node: JsonNode, path: tuple[str, ...]) -> JsonNode:
        if node.kind == "array":
            return node.model_copy(
                update={
                    "children": tuple(
                        visit(child, (*path, str(index)))
                        for index, child in enumerate(node.children)
                    )
                }
            )
        if node.kind != "object":
            return node
        children: list[JsonNode] = []
        for _, key, child in object_members(node):
            if key.value != "_birthDate":
                children.extend((key, visit(child, (*path, key.value))))
                continue
            if (
                member_text(node, "resourceType") != "Patient"
                or member(node, "birthDate") is not None
            ):
                raise ValueError(ERROR_COVERAGE)
            extensions = member(child, "extension")
            if (
                child.kind != "object"
                or len(child.children) != 2
                or extensions is None
                or extensions.kind != "array"
                or len(extensions.children) != 3
            ):
                raise ValueError(ERROR_COVERAGE)
            year = member_text(extensions.children[2], "valueDate")
            logical = BIRTH_BOUND_TEMPLATE.format(year=year)
            expected = fhir_birth_bound_metadata(logical)
            for actual, template in zip(
                extensions.children,
                cast(list[dict[str, str]], expected["extension"]),
                strict=True,
            ):
                if (
                    actual.kind != "object"
                    or len(actual.children) != 4
                    or {
                        name.value: value.value
                        for _, name, value in object_members(actual)
                    }
                    != template
                    or any(
                        value.kind != "string" for _, _, value in object_members(actual)
                    )
                ):
                    raise ValueError(ERROR_COVERAGE)
            transformed.append((*path, "birthDate"))
            children.extend(
                (
                    key.model_copy(update={"value": "birthDate"}),
                    JsonNode(
                        kind="string", start=child.start, end=child.end, value=logical
                    ),
                )
            )
        return node.model_copy(update={"children": tuple(children)})

    return visit(root, (FORMAT_FHIR,)), tuple(transformed)


def fhir_nodes(
    node: JsonNode, location: tuple[str, ...] = (FORMAT_FHIR,)
) -> Iterator[tuple[tuple[str, ...], JsonNode]]:
    """Object keys are fixed schema labels, so paths remain stable across writes."""
    yield location, node
    if node.kind == "object":
        for _, key, child in object_members(node):
            yield from fhir_nodes(child, (*location, key.value))
    elif node.kind == "array":
        for index, child in enumerate(node.children):
            yield from fhir_nodes(child, (*location, str(index)))


def fhir_resources(
    root: JsonNode,
) -> dict[tuple[str, ...], JsonNode]:
    if member_text(root, "resourceType") != "Bundle":
        raise ValueError(ERROR_STRUCTURE)
    resources = {
        path: node
        for path, node in fhir_nodes(root)
        if node.kind == "object" and member(node, "resourceType") is not None
    }
    for resource in resources.values():
        if member_text(resource, "resourceType") not in (
            "Bundle",
            "Patient",
            "Practitioner",
            "Encounter",
            "Condition",
            "Observation",
            "Specimen",
            "MedicationRequest",
            "DocumentReference",
        ):
            raise ValueError(ERROR_COVERAGE)
    return resources


def fhir_reference_slots(
    root: JsonNode,
) -> dict[tuple[str, ...], tuple[str, str, str, tuple[str, ...]]]:
    """Return canonical ID, retained syntax prefix, namespace and target location."""
    resources = fhir_resources(root)
    targets: dict[str, tuple[str, ...]] = {}
    slots: dict[tuple[str, ...], tuple[str, str, str, tuple[str, ...]]] = {}
    for path, node in resources.items():
        identifier = member_text(node, "id")
        if not identifier:
            continue
        if re.fullmatch(r"[A-Za-z0-9.-]{1,64}", identifier) is None:
            raise ValueError(ERROR_STRUCTURE)
        kind = member_text(node, "resourceType")
        namespace = f"fhir:{kind}"
        if "contained" in path:
            owner = path[: path.index("contained")]
            namespace += ":" + "/".join(owner)
        else:
            target_key = f"{kind}/{identifier}"
            if target_key in targets:
                raise ValueError(ERROR_STRUCTURE)
            targets[target_key] = path
        slots[(*path, "id")] = (identifier, "", namespace, path)
    for path, node in fhir_nodes(root):
        if node.kind != "object" or member(node, "fullUrl") is None:
            continue
        url = member_text(node, "fullUrl")
        target_path = (*path, "resource")
        target_slot = slots.get((*target_path, "id"))
        if target_slot is None or not url.startswith("urn:uuid:") or url in targets:
            raise ValueError(ERROR_COVERAGE)
        targets[url] = target_path
        slots[(*path, "fullUrl")] = (
            target_slot[0],
            "urn:uuid:",
            target_slot[2],
            target_path,
        )
    for path, node in fhir_nodes(root):
        if path[-1] != "reference" or node.kind != "string":
            continue
        reference = node.value
        if reference.startswith("#"):
            owners = [scope for scope in resources if path[: len(scope)] == scope]
            owner = max(owners, key=len)
            if "contained" in owner:
                owner = owner[: owner.index("contained")]
            matches = [
                scope
                for scope, resource in resources.items()
                if scope[: len(owner) + 1] == (*owner, "contained")
                and member_text(resource, "id") == reference[1:]
            ]
            if len(matches) != 1:
                raise ValueError(ERROR_COVERAGE)
            target = matches[0]
            prefix = "#"
        else:
            target = targets.get(reference, ())
            if not target:
                raise ValueError(ERROR_COVERAGE)
            prefix = (
                "urn:uuid:"
                if reference.startswith("urn:uuid:")
                else reference.rsplit("/", 1)[0] + "/"
            )
        target_slot = slots.get((*target, "id"))
        if target_slot is None:
            raise ValueError(ERROR_COVERAGE)
        slots[path] = (target_slot[0], prefix, target_slot[2], target)
    return slots


def _identifier_policy(node: JsonNode, *, provider: bool) -> ColumnPolicy:
    system = member_text(node, "system")
    if system == "http://hl7.org/fhir/sid/us-ssn":
        return ColumnPolicy(index=0, kind=FIELD_SSN, namespace=SSN_NAMESPACE)
    if system == "http://hl7.org/fhir/sid/us-npi":
        return ColumnPolicy(index=0, kind=FIELD_PROVIDER_ID, namespace=NPI_NAMESPACE)
    type_node = member(node, "type")
    if type_node and member_text(type_node, "text").casefold() in (
        "mrn",
        "medical record number",
    ):
        return ColumnPolicy(index=0, kind=FIELD_PATIENT_ID, namespace=MRN_NAMESPACE)
    return ColumnPolicy(
        index=0,
        kind=FIELD_IDENTIFIER,
        namespace=system
        or ("fhir:provider-identifier" if provider else "fhir:identifier"),
    )


def _resource_evidence(node: JsonNode, path: tuple[str, ...]) -> RowEvidence:
    kind = member_text(node, "resourceType")
    if kind not in ("Patient", "Practitioner"):
        return RowEvidence(patient=None, provider=None)
    names = member(node, "name")
    name = human_name(names.children[0]) if names and names.children else ""
    identifiers = member(node, "identifier")
    primary = None
    if identifiers:
        for identifier in identifiers.children:
            policy = _identifier_policy(identifier, provider=kind == "Practitioner")
            if policy.kind in (FIELD_PATIENT_ID, FIELD_PROVIDER_ID):
                primary = (member_text(identifier, "value"), policy.namespace)
                break
    birth = member_text(node, "birthDate") if kind == "Patient" else ""
    evidence = IdentityEvidence(
        role="patient" if kind == "Patient" else "provider",
        name=name,
        identifier=canonical_record_identifier(primary[0], primary[1])
        if primary
        else "",
        identifier_namespace=primary[1] if primary else "",
        birth_date=parse_date(birth).value if birth else None,
        context_key="/".join(path),
    )
    return RowEvidence(
        patient=evidence if kind == "Patient" else None,
        provider=evidence if kind == "Practitioner" else None,
    )


def fhir_contexts(root: JsonNode) -> dict[tuple[str, ...], RowEvidence]:
    resources = fhir_resources(root)
    slots = fhir_reference_slots(root)
    contexts = {
        path: _resource_evidence(node, path) for path, node in resources.items()
    }
    for path in resources:
        context = contexts[path]
        for field in ("subject", "patient"):
            slot = slots.get((*path, field, "reference"))
            if slot:
                person = contexts[slot[3]].patient
                if person:
                    context = context.model_copy(update={"patient": person})
        if "contained" in path:
            owner = path[: path.index("contained")]
            context = contexts[owner]
        contexts[path] = context
    references: dict[str, list[str]] = {}
    for path, node in resources.items():
        patient = contexts[path].patient
        if not patient:
            continue
        values = references.setdefault(patient.context_key, [])
        for child_path, child in fhir_nodes(node, path):
            if child.kind == "string" and _is_date(child_path[-1]):
                values.append(child.value)
    for path, context in contexts.items():
        if context.patient:
            dates = references.get(context.patient.context_key, [])
            latest = max((parse_date(value).value for value in dates), default=None)
            contexts[path] = context.model_copy(
                update={
                    "patient": context.patient.model_copy(
                        update={"reference_date": latest}
                    )
                }
            )
    return contexts


def _is_date(key: str) -> bool:
    return key in (
        "timestamp",
        "date",
        "recordedDate",
        "authoredOn",
        "issued",
        "lastUpdated",
        "start",
        "end",
        "creation",
        "onsetDateTime",
        "abatementDateTime",
    ) or key.endswith("DateTime")


def parse_fhir_narrative(value: str) -> etree._Element:
    parser = etree.XMLParser(resolve_entities=False, no_network=True, load_dtd=False)
    try:
        root = etree.fromstring(value.encode(TEXT_ENCODING), parser)
    except etree.XMLSyntaxError:
        raise ValueError(ERROR_STRUCTURE) from None
    if (
        root.getroottree().docinfo.doctype
        or root.tag != "{http://www.w3.org/1999/xhtml}div"
    ):
        raise ValueError(ERROR_COVERAGE)
    for element in root.iter():
        if (
            not isinstance(element.tag, str)
            or element.tag.removeprefix("{http://www.w3.org/1999/xhtml}")
            not in (
                "div",
                "p",
                "b",
                "i",
                "strong",
                "em",
                "span",
                "br",
                "ul",
                "ol",
                "li",
                "table",
                "thead",
                "tbody",
                "tr",
                "td",
                "th",
                "h1",
                "h2",
                "h3",
                "pre",
            )
            or element.attrib
        ):
            raise ValueError(ERROR_COVERAGE)
    return root


def fhir_narrative_groups(
    root: etree._Element,
) -> tuple[tuple[int, tuple[tuple[etree._Element, str], ...]], ...]:
    """Join inline runs in each visible block, including text split across tags."""
    positions = {element: index for index, element in enumerate(root.iter())}
    groups: dict[int, list[tuple[etree._Element, str]]] = {}

    def visit(element: etree._Element, owner: int) -> None:
        local = str(element.tag).rsplit("}", 1)[-1]
        if local in ("div", "p", "li", "td", "th", "h1", "h2", "h3", "pre"):
            owner = positions[element]
        if element.text is not None:
            groups.setdefault(owner, []).append((element, "text"))
        for child in element:
            visit(child, owner)
            if child.tail is not None:
                groups.setdefault(owner, []).append((child, "tail"))

    visit(root, 0)
    return tuple((index, tuple(fields)) for index, fields in sorted(groups.items()))


def attachment_bytes(node: JsonNode, resources: ResourceSettings) -> bytes:
    if member(node, "size") is not None or member(node, "hash") is not None:
        raise ValueError(ERROR_COVERAGE)
    data = member(node, "data")
    if data is None or data.kind != "string" or member(node, "url") is not None:
        raise ValueError(ERROR_COVERAGE)
    try:
        content = base64.b64decode(data.value, validate=True)
    except (ValueError, binascii.Error):
        raise ValueError(ERROR_STRUCTURE) from None
    if len(content) > resources.max_native_file_bytes:
        raise ValueError(ERROR_RESOURCE_LIMIT)
    return content


def read_fhir_attachment(
    node: JsonNode, resources: ResourceSettings, *, extract_evidence: bool = True
) -> NativeDocument:
    content = attachment_bytes(node, resources)
    content_type = member_text(node, "contentType")
    if content_type in ("image/png", "image/jpeg", "image/tiff"):
        expected_format = {
            "image/png": PIXEL_PNG_FORMAT,
            "image/jpeg": PIXEL_JPEG_FORMAT,
            "image/tiff": PIXEL_TIFF_FORMAT,
        }[content_type]
        try:
            with Image.open(BytesIO(content)) as image:
                if image.format != expected_format:
                    raise ValueError(ERROR_COVERAGE)
        except UnidentifiedImageError:
            raise ValueError(ERROR_STRUCTURE) from None
        return NativeDocument(
            records=(), images=(NativeImage(location=("image",), content=content),)
        )
    with TemporaryDirectory(prefix="redactor-fhir-") as folder:
        path = Path(folder) / "attachment"
        path.write_bytes(content)
        if content_type == "application/pdf":
            from redactor.formats.pdf import read_pdf

            return read_pdf(path, resources, extract_evidence=extract_evidence)
        if content_type == "application/json":
            from redactor.formats.json_document import read_json_document

            return read_json_document(
                path, resources, extract_evidence=extract_evidence
            )
    raise ValueError(ERROR_COVERAGE)


def read_fhir(
    path: Path, resources: ResourceSettings, *, extract_evidence: bool = True
) -> NativeDocument:
    if path.stat().st_size > resources.max_native_file_bytes:
        raise ValueError(ERROR_RESOURCE_LIMIT)
    root = parse_json_text(path.read_text(encoding=UTF8_BOM_ENCODING), resources)
    root, generalized = normalize_fhir_birth_bounds(root)
    if extract_evidence and generalized:
        raise ValueError(
            ERROR_COVERAGE
        )  # Already generalized inputs are not original DOB evidence.
    resource_nodes = fhir_resources(root)
    slots = fhir_reference_slots(root)
    contexts = fhir_contexts(root) if extract_evidence else {}
    records: list[NativeRecord] = []
    images: list[NativeImage] = []

    def add(
        value: str,
        location: tuple[str, ...],
        policy: ColumnPolicy,
        context: RowEvidence,
        scope: tuple[str, ...],
    ) -> None:
        records.append(
            NativeRecord(
                values=(value,),
                policies=(policy,),
                locations=(location,),
                evidence=context,
                context_scope="/".join(scope),
            )
        )

    def visit(
        node: JsonNode,
        location: tuple[str, ...],
        context: RowEvidence,
        scope: tuple[str, ...],
        parent: JsonNode | None = None,
        name_part: str = "",
    ) -> None:
        if location in resource_nodes:
            scope = location
            context = contexts.get(location, RowEvidence(patient=None, provider=None))
        if node.kind == "array":
            for index, child in enumerate(node.children):
                visit(
                    child,
                    (*location, str(index)),
                    context,
                    scope,
                    parent,
                    name_part="initial"
                    if name_part == "given" and index
                    else name_part,
                )
            return
        if node.kind == "object":
            if member(node, "reference"):
                slot = slots.get((*location, "reference"))
                if slot:
                    target_context = contexts.get(slot[3])
                    if target_context:
                        context = RowEvidence(
                            patient=target_context.patient or context.patient,
                            provider=target_context.provider or context.provider,
                        )
            is_attachment = member(node, "contentType") is not None and (
                member(node, "data") is not None or member(node, "url") is not None
            )
            if is_attachment:
                nested = read_fhir_attachment(
                    node, resources, extract_evidence=extract_evidence
                )
                prefix = (*location, "data", "attachment")
                records.extend(
                    record.model_copy(
                        update={
                            "locations": tuple(
                                (*prefix, *loc) for loc in record.locations
                            ),
                            "evidence": context,
                            "context_scope": "/".join(scope),
                        }
                    )
                    for record in nested.records
                )
                images.extend(
                    image.model_copy(update={"location": (*prefix, *image.location)})
                    for image in nested.images
                )
            if member(node, "data") is not None and not is_attachment:
                raise ValueError(ERROR_COVERAGE)
            if (
                len(location) > 1
                and location[-1].isdigit()
                and location[-2] == "extension"
            ):
                extension_value = member(node, "valueString")
                if (
                    member_text(node, "url")
                    != "http://hl7.org/fhir/StructureDefinition/patient-mothersMaidenName"
                    or extension_value is None
                    or extension_value.kind != "string"
                    or any(
                        key.value not in ("url", "valueString", "id")
                        for _, key, _ in object_members(node)
                    )
                ):
                    raise ValueError(ERROR_COVERAGE)
            if member(node, "url") is not None and "extension" in location:
                if (
                    member_text(node, "url")
                    != "http://hl7.org/fhir/StructureDefinition/patient-mothersMaidenName"
                ):
                    raise ValueError(ERROR_COVERAGE)
            for _, key, child in object_members(node):
                if re.fullmatch(r"_?[A-Za-z][A-Za-z0-9]*", key.value) is None:
                    raise ValueError(ERROR_STRUCTURE)
                if key.value not in (
                    "resourceType",
                    "id",
                    "type",
                    "timestamp",
                    "entry",
                    "fullUrl",
                    "resource",
                    "text",
                    "status",
                    "div",
                    "extension",
                    "url",
                    "valueString",
                    "identifier",
                    "system",
                    "value",
                    "name",
                    "use",
                    "family",
                    "given",
                    "prefix",
                    "suffix",
                    "telecom",
                    "gender",
                    "birthDate",
                    "address",
                    "line",
                    "city",
                    "district",
                    "state",
                    "postalCode",
                    "country",
                    "generalPractitioner",
                    "reference",
                    "display",
                    "class",
                    "subject",
                    "patient",
                    "participant",
                    "individual",
                    "period",
                    "start",
                    "end",
                    "code",
                    "coding",
                    "onsetAge",
                    "unit",
                    "recordedDate",
                    "effectiveDateTime",
                    "valueQuantity",
                    "contained",
                    "accessionIdentifier",
                    "collection",
                    "collectedDateTime",
                    "specimen",
                    "intent",
                    "medicationCodeableConcept",
                    "requester",
                    "authoredOn",
                    "date",
                    "content",
                    "attachment",
                    "contentType",
                    "title",
                    "data",
                    "size",
                    "hash",
                    "creation",
                    "language",
                    "meta",
                    "versionId",
                    "lastUpdated",
                    "profile",
                    "security",
                    "tag",
                    "note",
                    "authorString",
                    "authorReference",
                    "time",
                    "issued",
                    "onsetDateTime",
                    "abatementDateTime",
                    "effectivePeriod",
                    "valueString",
                    "valueBoolean",
                    "valueInteger",
                    "valueCodeableConcept",
                    "interpretation",
                    "referenceRange",
                    "low",
                    "high",
                    "component",
                    "performer",
                    "encounter",
                    "category",
                    "bodySite",
                    "clinicalStatus",
                    "verificationStatus",
                    "clinicalStatus",
                    "severity",
                    "doseQuantity",
                    "dosageInstruction",
                    "method",
                    "route",
                    "timing",
                    "repeat",
                    "frequency",
                    "periodUnit",
                    "asNeededBoolean",
                    "active",
                    "deceasedBoolean",
                    "multipleBirthBoolean",
                    "maritalStatus",
                    "managingOrganization",
                    "contact",
                    "relationship",
                ):
                    raise ValueError(ERROR_COVERAGE)
                if key.value.startswith("_") or key.value in (
                    "contact",
                    "modifierExtension",
                    "signature",
                    "photo",
                    "presentedForm",
                ):
                    raise ValueError(ERROR_COVERAGE)
                if is_attachment and key.value == "data":
                    continue
                part = (
                    key.value
                    if "name" in location and key.value in ("given", "family")
                    else ""
                )
                visit(child, (*location, key.value), context, scope, node, part)
            return
        if node.kind != "string":
            if (
                node.kind == "number"
                and any(part.endswith("Age") for part in location)
                and float(node.value) >= 90
            ):
                raise ValueError(ERROR_COVERAGE)
            return
        field_name = location[-1]
        semantic_key = location[-2] if field_name.isdigit() else field_name
        policy = ColumnPolicy(index=0, kind=FIELD_TEXT)
        if location in slots:
            value, _, namespace, _ = slots[location]
            add(
                value,
                location,
                ColumnPolicy(index=0, kind=FIELD_IDENTIFIER, namespace=namespace),
                context,
                scope,
            )
            return
        if field_name == "div":
            narrative = parse_fhir_narrative(node.value)
            for index, fields in fhir_narrative_groups(narrative):
                add(
                    "".join(
                        getattr(element, attribute) or ""
                        for element, attribute in fields
                    ),
                    (*location, "xhtml", str(index)),
                    policy,
                    context,
                    scope,
                )
            return
        if semantic_key == "resourceType":
            return
        if (
            semantic_key == "text"
            and "identifier" in location
            and node.value.casefold()
            in (
                "mrn",
                "medical record number",
                "npi",
                "ssn",
                "social security number",
            )
        ):
            return
        if semantic_key == "system":
            if not (
                node.value
                in (
                    "phone",
                    "email",
                    "fax",
                    "pager",
                    "url",
                    "sms",
                    "other",
                    "http://hl7.org/fhir/sid/us-ssn",
                    "http://hl7.org/fhir/sid/us-npi",
                    "http://hl7.org/fhir/sid/icd-10-cm",
                    "http://loinc.org",
                    "http://unitsofmeasure.org",
                    "http://www.nlm.nih.gov/research/umls/rxnorm",
                    "http://terminology.hl7.org/CodeSystem/v3-ActCode",
                )
                or re.fullmatch(r"urn:oid:[0-9]+(?:\.[0-9]+)+", node.value)
            ):
                raise ValueError(ERROR_COVERAGE)
            return
        if semantic_key == "url" and "extension" in location:
            return
        if semantic_key == "contentType":
            if node.value not in (
                "application/pdf",
                "application/json",
                "image/png",
                "image/jpeg",
                "image/tiff",
            ):
                raise ValueError(ERROR_COVERAGE)
            return
        if semantic_key == "code" and parent is not None and member(parent, "system"):
            system = member_text(parent, "system")
            clinical_namespace = {
                "http://hl7.org/fhir/sid/icd-10-cm": "icd",
                "http://loinc.org": "loinc",
                "http://www.nlm.nih.gov/research/umls/rxnorm": "rxnorm",
                "http://unitsofmeasure.org": "unit",
            }.get(system)
            if clinical_namespace:
                policy = ColumnPolicy(
                    index=0, kind=FIELD_CLINICAL, namespace=clinical_namespace
                )
            elif (
                system == "http://terminology.hl7.org/CodeSystem/v3-ActCode"
                and node.value in ("AMB", "IMP", "EMER", "OBSENC", "HH", "VR")
            ):
                return
            else:
                raise ValueError(ERROR_COVERAGE)
        elif (
            semantic_key == "display"
            and parent is not None
            and member_text(parent, "system") == "http://loinc.org"
        ):
            try:
                validate_clinical_field(node.value, LAB_DESCRIPTION_NAMESPACE)
            except ValueError:
                pass  # Unknown descriptions retain complete contextual assessment.
            else:
                policy = ColumnPolicy(
                    index=0, kind=FIELD_CLINICAL, namespace=LAB_DESCRIPTION_NAMESPACE
                )
        elif (
            semantic_key == "display"
            and parent is not None
            and member_text(parent, "system")
            == "http://www.nlm.nih.gov/research/umls/rxnorm"
        ):
            try:
                validate_clinical_field(node.value, MEDICATION_DISPLAY_NAMESPACE)
            except ValueError:
                pass
            else:
                policy = ColumnPolicy(
                    index=0, kind=FIELD_CLINICAL, namespace=MEDICATION_DISPLAY_NAMESPACE
                )
        elif name_part:
            policy = ColumnPolicy(
                index=0,
                kind=FIELD_PROVIDER_NAME
                if member_text(resource_nodes[scope], "resourceType") == "Practitioner"
                else FIELD_PATIENT_NAME,
                name_part=cast(Literal["given", "family", "initial"], name_part),
            )
        elif (
            semantic_key == "display"
            and parent is not None
            and member(parent, "reference")
        ):
            target = slots[(*location[:-1], "reference")][3]
            kind = member_text(resource_nodes[target], "resourceType")
            if kind in ("Patient", "Practitioner"):
                policy = ColumnPolicy(
                    index=0,
                    kind=FIELD_PATIENT_NAME
                    if kind == "Patient"
                    else FIELD_PROVIDER_NAME,
                )
        elif semantic_key == "text" and "name" in location:
            policy = ColumnPolicy(
                index=0,
                kind=FIELD_PROVIDER_NAME
                if member_text(resource_nodes[scope], "resourceType") == "Practitioner"
                else FIELD_PATIENT_NAME,
            )
        elif (
            semantic_key == "value"
            and parent is not None
            and any("identifier" in part.casefold() for part in location)
        ):
            policy = _identifier_policy(
                parent,
                provider=member_text(resource_nodes[scope], "resourceType")
                == "Practitioner",
            )
        elif semantic_key == "value" and "telecom" in location and parent is not None:
            system = member_text(parent, "system")
            if system not in ("phone", "fax", "sms", "email"):
                raise ValueError(ERROR_COVERAGE)
            policy = ColumnPolicy(
                index=0, kind=FIELD_EMAIL if system == "email" else FIELD_PHONE
            )
        elif semantic_key == "valueString" and "extension" in location:
            policy = ColumnPolicy(index=0, kind=FIELD_RELATIVE_NAME)
        elif semantic_key == "id":
            policy = ColumnPolicy(
                index=0, kind=FIELD_IDENTIFIER, namespace="fhir:element-id"
            )
        elif semantic_key == "authorString":
            policy = ColumnPolicy(index=0, kind=FIELD_PERSON_NAME)
        elif semantic_key == "versionId":
            policy = ColumnPolicy(
                index=0, kind=FIELD_IDENTIFIER, namespace="fhir:version"
            )
        elif semantic_key == "birthDate":
            policy = ColumnPolicy(
                index=0,
                kind=FIELD_BIRTH_DATE
                if member_text(resource_nodes[scope], "resourceType") == "Patient"
                else FIELD_DATE,
                supports_date_bounds=True,
            )
        elif _is_date(semantic_key):
            policy = ColumnPolicy(index=0, kind=FIELD_DATE)
        elif semantic_key == "line" and "address" in location:
            policy = ColumnPolicy(index=0, kind=FIELD_ADDRESS)
        elif semantic_key == "city":
            policy = ColumnPolicy(index=0, kind=FIELD_LOCATION)
        elif semantic_key == "postalCode":
            policy = ColumnPolicy(index=0, kind=FIELD_ZIP)
        elif semantic_key in ("state", "gender", "unit"):
            policy = ColumnPolicy(
                index=0,
                kind=FIELD_CLINICAL,
                namespace={"gender": "sex"}.get(semantic_key, semantic_key),
            )
        add(node.value, location, policy, context, scope)

    visit(
        root, (FORMAT_FHIR,), RowEvidence(patient=None, provider=None), (FORMAT_FHIR,)
    )
    return NativeDocument(records=tuple(records), images=tuple(images))


def write_fhir(
    original: Path,
    output: Path,
    replacements: dict[tuple[str, ...], str],
    images: dict[tuple[str, ...], bytes],
    resources: ResourceSettings,
) -> None:
    text = original.read_text(encoding=UTF8_BOM_ENCODING)
    root = parse_json_text(text, resources)
    slots = fhir_reference_slots(root)
    edits: list[tuple[int, int, str]] = []
    used: set[tuple[str, ...]] = set()
    used_images: set[tuple[str, ...]] = set()
    for location, node in fhir_nodes(root):
        if (
            node.kind == "object"
            and member(node, "contentType") is not None
            and member(node, "data") is not None
        ):
            prefix = (*location, "data", "attachment")
            local_changes = {
                key[len(prefix) :]: value
                for key, value in replacements.items()
                if key[: len(prefix)] == prefix
            }
            local_images = {
                key[len(prefix) :]: value
                for key, value in images.items()
                if key[: len(prefix)] == prefix
            }
            used.update(key for key in replacements if key[: len(prefix)] == prefix)
            used_images.update(key for key in images if key[: len(prefix)] == prefix)
            content = _write_attachment(node, resources, local_changes, local_images)
            data = member(node, "data")
            assert data is not None
            edits.append(
                (
                    data.start,
                    data.end,
                    json.dumps(base64.b64encode(content).decode("ascii")),
                )
            )
        elif node.kind == "string" and location[-1] == "div":
            narrative = parse_fhir_narrative(node.value)
            changed = False
            for index, fields in fhir_narrative_groups(narrative):
                key = (*location, "xhtml", str(index))
                if key in replacements:
                    runs = tuple(Element("run") for _ in fields)
                    for run, (element, attribute) in zip(runs, fields, strict=True):
                        run.text = getattr(element, attribute)
                    replace_text_nodes(runs, replacements[key])
                    for run, (element, attribute) in zip(runs, fields, strict=True):
                        setattr(element, attribute, run.text)
                    used.add(key)
                    changed = True
            if changed:
                edits.append(
                    (
                        node.start,
                        node.end,
                        json.dumps(
                            etree.tostring(narrative, encoding="unicode"),
                            ensure_ascii=False,
                        ),
                    )
                )
        elif location in replacements:
            if node.kind != "string":
                raise ValueError(ERROR_STRUCTURE)
            value = replacements[location]
            if location[-1] == "birthDate" and value.startswith(
                BIRTH_BOUND_TEMPLATE.split("{", 1)[0]
            ):
                parent = dict(fhir_nodes(root))[location[:-1]]
                if (
                    member_text(parent, "resourceType") != "Patient"
                    or member(parent, "_birthDate") is not None
                ):
                    raise ValueError(ERROR_COVERAGE)
                birth_key = next(
                    field for _, field, child in object_members(parent) if child is node
                )
                edits.append((birth_key.start, birth_key.end, json.dumps("_birthDate")))
                edits.append(
                    (node.start, node.end, json.dumps(fhir_birth_bound_metadata(value)))
                )
                used.add(location)
                continue
            if location in slots:
                value = slots[location][1] + value
            edits.append((node.start, node.end, json.dumps(value, ensure_ascii=False)))
            used.add(location)
    if used != set(replacements) or used_images != set(images):
        raise ValueError(ERROR_COVERAGE)
    cursor = 0
    pieces: list[str] = []
    for start, end, replacement in sorted(edits):
        if start < cursor:
            raise ValueError(ERROR_COVERAGE)
        pieces.extend((text[cursor:start], replacement))
        cursor = end
    pieces.append(text[cursor:])
    result = "".join(pieces)
    parse_json_text(result, resources)
    output.write_text(result, encoding=TEXT_ENCODING)


def _write_attachment(
    node: JsonNode,
    resources: ResourceSettings,
    replacements: dict[tuple[str, ...], str],
    images: dict[tuple[str, ...], bytes],
) -> bytes:
    content = attachment_bytes(node, resources)
    content_type = member_text(node, "contentType")
    if content_type in ("image/png", "image/jpeg", "image/tiff"):
        if replacements or set(images) - {("image",)}:
            raise ValueError(ERROR_COVERAGE)
        return images.get(("image",), content)
    with TemporaryDirectory(prefix="redactor-fhir-") as folder:
        source, saved = Path(folder) / "source", Path(folder) / "saved"
        source.write_bytes(content)
        if content_type == "application/pdf":
            from redactor.formats.pdf import write_pdf

            write_pdf(source, saved, replacements, images)
        elif content_type == "application/json":
            from redactor.formats.json_document import write_json_document

            if images:
                raise ValueError(ERROR_COVERAGE)
            write_json_document(source, saved, replacements, resources)
        else:
            raise ValueError(ERROR_COVERAGE)
        return saved.read_bytes()
