"""Compare saved DICOM attributes outside the assessed text and pixel surfaces."""

from pathlib import Path

import pydicom

from redactor.formats.dicom import dicom_elements, normalize_dicom_age_bounds
from redactor.schemas.native import NativeDocument
from redactor.utils.constants import DICOM_FILE_META_LOCATION, DICOM_PIXEL_TAG
from redactor.utils.errors import ERROR_CLINICAL_CHANGED, ERROR_COVERAGE


def check_dicom_structure(
    original: Path, output: Path, document: NativeDocument
) -> None:
    before, after = pydicom.dcmread(original), pydicom.dcmread(output)
    normalize_dicom_age_bounds(before, allow_generated=False)
    normalize_dicom_age_bounds(after, allow_generated=True)
    if after.preamble != bytes(128):
        raise ValueError(ERROR_COVERAGE)
    locations = {
        location for record in document.records for location in record.locations
    }
    left = dict(dicom_elements(before))
    right = dict(dicom_elements(after))
    if left.keys() != right.keys():
        raise ValueError(ERROR_COVERAGE)
    for location, element in left.items():
        saved = right[location]
        if saved.VR != element.VR:
            raise ValueError(ERROR_COVERAGE)
        if (
            location not in locations
            and int(element.tag) != DICOM_PIXEL_TAG
            and saved.value != element.value
        ):
            raise ValueError(ERROR_CLINICAL_CHANGED)
    for element in before.file_meta:
        if element.tag not in after.file_meta:
            raise ValueError(ERROR_COVERAGE)
        if element.keyword in (
            "FileMetaInformationGroupLength",
            "MediaStorageSOPInstanceUID",
            "TransferSyntaxUID",
        ):
            continue
        location = (DICOM_FILE_META_LOCATION, f"{int(element.tag):08x}")
        if location not in locations and after.file_meta[element.tag] != element:
            raise ValueError(ERROR_CLINICAL_CHANGED)
    if set(before.file_meta.keys()) != set(after.file_meta.keys()):
        raise ValueError(ERROR_COVERAGE)
    if after.file_meta.MediaStorageSOPInstanceUID != after.SOPInstanceUID:
        raise ValueError(ERROR_COVERAGE)
