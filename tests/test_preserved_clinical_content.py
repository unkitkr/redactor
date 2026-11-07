"""Scale expressions, software attribution and vendor identifiers stay clinical."""

from pathlib import Path

import pydicom
import pymupdf
from pydicom.dataset import FileDataset, FileMetaDataset

from redactor.formats.dicom import read_dicom, write_dicom
from redactor.formats.pdf import read_pdf
from redactor.policy.identifiers import replace_identifier
from redactor.policy.text_patterns import clinical_ranges
from redactor.schemas.configuration import ResourceSettings
from redactor.utils.constants import (
    APPLICATION_NAMESPACE,
    DICOM_PRIVATE_CREATOR_NAMESPACE,
    FIELD_CLINICAL,
    FIELD_IDENTIFIER,
    FIELD_TEXT,
    PDF_METADATA_PART,
)
from redactor.verification.dicom import check_dicom_structure


def test_scale_stage_expressions_are_protected_clinical_text() -> None:
    line = "Assessment: Parkinson's disease (G20), Hoehn and Yahr stage 3."
    spans = clinical_ranges(line)
    scale = next(
        span
        for span in spans
        if "Hoehn and Yahr stage 3" in line[span.start : span.end]
    )
    assert line[scale.start : scale.end].endswith("Hoehn and Yahr stage 3")
    for token in ("Hoehn", "Yahr"):
        start = line.index(token)
        assert scale.start <= start and start + len(token) <= scale.end
    # A name that merely precedes a stage qualifier is never protected.
    plain = "Kowalczyk stage 3."
    assert all(
        "Kowalczyk" not in plain[span.start : span.end]
        for span in clinical_ranges(plain)
    )


def test_pdf_software_attribution_is_clinical_but_facilities_stay_text(
    tmp_path: Path,
) -> None:
    producers = {
        "software": "ReportLab PDF Library - www.reportlab.com",
        "facility": "Harbor Radiology Department",
    }
    policies = {}
    for name, producer in producers.items():
        source = tmp_path / f"{name}.pdf"
        with pymupdf.open() as pdf:
            pdf.new_page().insert_text((50, 60), "Clinical note", fontsize=11)
            pdf.set_metadata({"producer": producer, "creator": producer})
            pdf.save(source)
        document = read_pdf(source, ResourceSettings(), extract_evidence=False)
        record = next(
            record
            for record in document.records
            if record.locations[0][0] == PDF_METADATA_PART
        )
        for location, policy in zip(record.locations, record.policies, strict=True):
            if location[-1] in ("producer", "creator"):
                policies[(name, location[-1])] = policy
    assert policies[("software", "producer")].kind == FIELD_CLINICAL
    assert policies[("software", "producer")].namespace == APPLICATION_NAMESPACE
    assert policies[("software", "creator")].kind == FIELD_CLINICAL
    assert policies[("software", "creator")].namespace == APPLICATION_NAMESPACE
    assert policies[("facility", "producer")].kind == FIELD_TEXT
    assert policies[("facility", "producer")].namespace == ""
    assert policies[("facility", "creator")].kind == FIELD_TEXT


def test_dicom_private_creators_are_pseudonymized_identifiers(
    tmp_path: Path,
) -> None:
    source, output = tmp_path / "source.dcm", tmp_path / "output.dcm"
    metadata = FileMetaDataset()
    metadata.TransferSyntaxUID = pydicom.uid.ExplicitVRLittleEndian
    metadata.MediaStorageSOPClassUID = pydicom.uid.SecondaryCaptureImageStorage
    metadata.MediaStorageSOPInstanceUID = pydicom.uid.UID("2.25.123456")
    dataset = FileDataset(str(source), {}, file_meta=metadata, preamble=bytes(128))
    dataset.SOPClassUID = metadata.MediaStorageSOPClassUID
    dataset.SOPInstanceUID = metadata.MediaStorageSOPInstanceUID
    dataset.PatientName = "Keller^Amina"
    dataset.PatientID = "90123"
    dataset.add_new((0x0011, 0x0010), "LO", "VENDOR_PACS")
    dataset.add_new((0x0011, 0x1001), "LO", "Keller, Amina 90123")
    pydicom.dcmwrite(source, dataset, enforce_file_format=True)
    document = read_dicom(source, ResourceSettings())
    records = {
        record.locations[0]: record
        for record in document.records
        if len(record.locations[0]) == 1
    }
    creator, private_data = records[("00110010",)], records[("00111001",)]
    assert creator.policies[0].kind == FIELD_IDENTIFIER
    assert creator.policies[0].namespace == DICOM_PRIVATE_CREATOR_NAMESPACE
    assert creator.field_labels == ()
    assert private_data.policies[0].kind == FIELD_TEXT
    replacement = replace_identifier(
        creator.values[0], bytes(range(32)), namespace=DICOM_PRIVATE_CREATOR_NAMESPACE
    )
    assert replacement.isdigit() and replacement != creator.values[0]
    write_dicom(source, output, {("00110010",): replacement}, {})
    check_dicom_structure(source, output, document)
    saved = pydicom.dcmread(output)
    assert str(saved[(0x0011, 0x0010)].value) == replacement
    reread = read_dicom(output, ResourceSettings(), extract_evidence=False)
    saved_creator = next(
        record for record in reread.records if record.locations[0] == ("00110010",)
    )
    assert saved_creator.policies[0].kind == FIELD_IDENTIFIER
    assert saved_creator.policies[0].namespace == DICOM_PRIVATE_CREATOR_NAMESPACE
