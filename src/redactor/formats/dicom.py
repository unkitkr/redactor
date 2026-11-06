"""Traverse DICOM sequences and preserve native attributes and unmasked pixels."""

import io
from collections.abc import Iterator
from pathlib import Path
from typing import cast

import numpy as np
import pydicom
from PIL import Image
from pydicom.dataelem import DataElement
from pydicom.dataset import Dataset

from redactor.identity.tabular import row_evidence
from redactor.schemas.configuration import ResourceSettings
from redactor.schemas.native import NativeDocument, NativeImage, NativeRecord
from redactor.schemas.redaction import ColumnPolicy, FieldKind
from redactor.utils.constants import (
    DICOM_BINARY_VRS,
    DICOM_CONTEXT,
    DICOM_FILE_META_LOCATION,
    DICOM_IDENTITY_FIELDS,
    DICOM_PIXEL_LOCATION,
    DICOM_PIXEL_TAG,
    DICOM_RESERVED_ATTRIBUTES,
    DICOM_SCHEMA_UID_FIELDS,
    DICOM_STRING_LIMITS,
    DICOM_TEXT_VRS,
    DICOM_UID_NAMESPACE,
    DICOM_UID_PREFIX,
    FIELD_AGE,
    FIELD_DATE,
    FIELD_IDENTIFIER,
    FIELD_PERSON_NAME,
    FIELD_TEXT,
    PIXEL_PNG_FORMAT,
)
from redactor.utils.errors import ERROR_COVERAGE, ERROR_RESOURCE_LIMIT, ERROR_STRUCTURE


def dicom_elements(
    dataset: Dataset, path: tuple[str, ...] = ()
) -> Iterator[tuple[tuple[str, ...], DataElement]]:
    for element in dataset:
        location = (*path, f"{int(element.tag):08x}")
        if element.keyword in DICOM_RESERVED_ATTRIBUTES:
            raise ValueError(ERROR_COVERAGE)
        if element.VR == "SQ":
            for index, child in enumerate(element.value):
                yield from dicom_elements(child, (*location, str(index)))
        else:
            yield location, element


def dicom_record(
    location: tuple[str, ...], element: DataElement
) -> NativeRecord | None:
    if element.VR not in DICOM_TEXT_VRS or element.keyword in DICOM_SCHEMA_UID_FIELDS:
        return None
    if element.VM > 1:
        raise ValueError(ERROR_COVERAGE)
    value = str(element.value)
    fields = {
        name: (kind, namespace) for name, kind, namespace in DICOM_IDENTITY_FIELDS
    }
    kind, namespace = fields.get(element.keyword, (FIELD_TEXT, ""))
    prefix = ""
    if element.VR == "UI":
        kind, namespace, prefix = (
            FIELD_IDENTIFIER,
            DICOM_UID_NAMESPACE,
            DICOM_UID_PREFIX,
        )
    elif element.VR in ("DA", "DT") and element.keyword != "PatientBirthDate":
        kind = FIELD_DATE
    elif element.VR == "PN" and element.keyword != "PatientName":
        kind = FIELD_PERSON_NAME
    elif element.VR == "AS":
        if len(value) != 4 or not value[:3].isdigit() or value[-1] != "Y":
            raise ValueError(ERROR_COVERAGE)
        value, kind = str(int(value[:3])), FIELD_AGE
    elif element.VR in ("CS", "TM"):
        return None  # Enumerated codes and time-of-day are preserved byte-for-byte.
    if element.VR == "PN":
        if "=" in value:
            raise ValueError(ERROR_COVERAGE)
        parts = value.split("^")
        value = " ".join((*parts[1:], parts[0])).strip()
    return NativeRecord(
        values=(value,),
        policies=(
            ColumnPolicy(
                index=0,
                kind=cast(FieldKind, kind),
                namespace=namespace,
                identifier_prefix=prefix,
                supports_date_bounds=False,
            ),
        ),
        locations=(location,),
    )


def read_dicom(
    path: Path, resources: ResourceSettings, *, extract_evidence: bool = True
) -> NativeDocument:
    dataset = pydicom.dcmread(path)
    records = []
    for element in dataset.file_meta:
        if element.keyword in DICOM_SCHEMA_UID_FIELDS or element.keyword in (
            "MediaStorageSOPInstanceUID",
            "FileMetaInformationVersion",
            "FileMetaInformationGroupLength",
        ):
            continue
        record = dicom_record(
            (DICOM_FILE_META_LOCATION, f"{int(element.tag):08x}"), element
        )
        if record is None:
            raise ValueError(ERROR_COVERAGE)
        records.append(record)
    for location, element in dicom_elements(dataset):
        if (element.VR in DICOM_BINARY_VRS and int(element.tag) != DICOM_PIXEL_TAG) or (
            int(element.tag) == DICOM_PIXEL_TAG and len(location) != 1
        ):
            raise ValueError(ERROR_COVERAGE)
        if element.tag.is_private and element.VR in ("CS", "TM"):
            raise ValueError(ERROR_COVERAGE)
        if element.tag.is_private and element.VR not in DICOM_TEXT_VRS:
            raise ValueError(ERROR_COVERAGE)
        if (
            0x6000 <= element.tag.group <= 0x60FF
            or element.keyword == "IconImageSequence"
        ):
            raise ValueError(ERROR_COVERAGE)
        record = dicom_record(location, element)
        if record is not None:
            records.append(record)
    # Demographic fields form the explicit patient context for every nested item.
    identifying = [record for record in records if len(record.locations[0]) == 1]
    values = tuple(record.values[0] for record in identifying)
    policies = tuple(
        record.policies[0].model_copy(update={"index": index})
        for index, record in enumerate(identifying)
    )
    evidence = (
        row_evidence(values, policies, DICOM_CONTEXT, 0) if extract_evidence else None
    )
    records = [
        record.model_copy(update={"evidence": evidence, "context_scope": DICOM_CONTEXT})
        for record in records
    ]
    images: list[NativeImage] = []
    if DICOM_PIXEL_TAG in dataset:
        if (
            dataset.BitsAllocated != 8
            or dataset.PixelRepresentation != 0
            or dataset.PhotometricInterpretation != "MONOCHROME2"
        ):
            raise ValueError(ERROR_COVERAGE)
        if (
            int(dataset.Rows)
            * int(dataset.Columns)
            * int(getattr(dataset, "NumberOfFrames", 1))
            > resources.max_image_pixels
        ):
            raise ValueError(ERROR_RESOURCE_LIMIT)
        pixels = dataset.pixel_array
        frames = pixels[np.newaxis] if pixels.ndim == 2 else pixels
        if frames.ndim != 3 or frames.size > resources.max_image_pixels:
            raise ValueError(ERROR_RESOURCE_LIMIT)
        for index, frame in enumerate(frames):
            target = io.BytesIO()
            Image.fromarray(frame).convert("RGB").save(target, format=PIXEL_PNG_FORMAT)
            images.append(
                NativeImage(
                    location=(DICOM_PIXEL_LOCATION, str(index)),
                    content=target.getvalue(),
                )
            )
    return NativeDocument(records=tuple(records), images=tuple(images))


def write_dicom(
    original: Path,
    output: Path,
    replacements: dict[tuple[str, ...], str],
    images: dict[tuple[str, ...], bytes],
) -> None:
    dataset = pydicom.dcmread(original)
    used: set[tuple[str, ...]] = set()
    elements = (
        *dicom_elements(dataset),
        *dicom_elements(dataset.file_meta, (DICOM_FILE_META_LOCATION,)),
    )
    for location, element in elements:
        if location not in replacements:
            continue
        value = replacements[location]
        if element.VR == "PN":
            parts = value.split()
            value = "^".join((parts[-1], " ".join(parts[:-1]))) if parts else ""
        elif element.VR == "AS":
            if not value.isdigit():
                raise ValueError(ERROR_COVERAGE)
            value = f"{int(value):03}Y"
        limit = dict(DICOM_STRING_LIMITS).get(element.VR)
        if limit is not None and len(value) > limit:
            raise ValueError(ERROR_COVERAGE)
        element.value = value
        used.add(location)
    if used != set(replacements):
        raise ValueError(ERROR_COVERAGE)
    if images:
        frames = []
        for index in range(int(getattr(dataset, "NumberOfFrames", 1))):
            with Image.open(
                io.BytesIO(images[(DICOM_PIXEL_LOCATION, str(index))])
            ) as image:
                rgb = np.array(image.convert("RGB"))
                if not np.array_equal(rgb[:, :, 0], rgb[:, :, 1]) or not np.array_equal(
                    rgb[:, :, 0], rgb[:, :, 2]
                ):
                    raise ValueError(ERROR_STRUCTURE)
                frames.append(rgb[:, :, 0])
        dataset.PixelData = np.stack(frames).tobytes()
        dataset.file_meta.TransferSyntaxUID = pydicom.uid.ExplicitVRLittleEndian
    dataset.file_meta.MediaStorageSOPInstanceUID = dataset.SOPInstanceUID
    dataset.preamble = bytes(128)
    pydicom.dcmwrite(output, dataset, enforce_file_format=True)
