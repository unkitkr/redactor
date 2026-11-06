"""Round-trip native DICOM sequences, UIDs, and protected clinical pixels."""

import io
import sqlite3
from pathlib import Path

import numpy as np
import pydicom
import pytest
from PIL import Image
from pydicom.dataset import Dataset, FileDataset, FileMetaDataset

from redactor.formats.dicom import read_dicom, write_dicom
from redactor.schemas.configuration import ResourceSettings
from redactor.verification.dicom import check_dicom_structure


def test_dicom_native_round_trip_and_saved_clinical_damage(tmp_path: Path) -> None:
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
    dataset.PatientBirthDate = "19720304"
    dataset.StudyDate = "20240312"
    dataset.Modality = "OT"
    dataset.Rows, dataset.Columns = 16, 16
    dataset.SamplesPerPixel = 1
    dataset.PhotometricInterpretation = "MONOCHROME2"
    dataset.BitsAllocated = dataset.BitsStored = 8
    dataset.HighBit = 7
    dataset.PixelRepresentation = 0
    pixels = np.arange(256, dtype=np.uint8).reshape(16, 16)
    dataset.PixelData = pixels.tobytes()
    nested = Dataset()
    nested.ReferencedSOPClassUID = dataset.SOPClassUID
    nested.ReferencedSOPInstanceUID = dataset.SOPInstanceUID
    dataset.ReferencedImageSequence = [nested]
    pydicom.dcmwrite(source, dataset, enforce_file_format=True)
    document = read_dicom(source, ResourceSettings())
    replacements = {
        location: (
            "2.25.987654"
            if policy.namespace == "dicom_uid"
            else "Nadia Stone"
            if value == "Amina Keller"
            else "81234"
            if value == "90123"
            else "19720404"
            if value == "19720304"
            else "20240412"
            if value == "20240312"
            else value
        )
        for record in document.records
        for location, value, policy in zip(
            record.locations, record.values, record.policies, strict=True
        )
    }
    image = Image.open(io.BytesIO(document.images[0].content))
    image.putpixel((2, 2), (0, 0, 0))
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    write_dicom(
        source, output, replacements, {document.images[0].location: buffer.getvalue()}
    )
    check_dicom_structure(source, output, document)
    saved = pydicom.dcmread(output)
    assert str(saved.PatientName) == "Stone^Nadia"
    assert saved.PatientBirthDate == "19720404"
    assert (
        saved.SOPInstanceUID
        == saved.ReferencedImageSequence[0].ReferencedSOPInstanceUID
    )
    assert saved.file_meta.MediaStorageSOPInstanceUID == saved.SOPInstanceUID
    pixels[2, 2] = 0
    assert np.array_equal(saved.pixel_array, pixels)
    assert len(
        read_dicom(output, ResourceSettings(), extract_evidence=False).records
    ) == len(document.records)
    saved.Modality = "MR"
    pydicom.dcmwrite(output, saved, enforce_file_format=True)
    with pytest.raises(ValueError):
        check_dicom_structure(source, output, document)

    for tag, vr, content in (
        ((0x0042, 0x0011), "OB", b"Unassessed patient text"),
        ((0x0011, 0x1010), "CS", "ALICE"),
    ):
        changed = pydicom.dcmread(source)
        changed.add_new(tag, vr, content)
        pydicom.dcmwrite(output, changed, enforce_file_format=True)
        with pytest.raises(ValueError):
            read_dicom(output, ResourceSettings())


def test_dicom_age_band_roundtrip_and_saved_bound_tampering(
    connection: sqlite3.Connection, tmp_path: Path
) -> None:
    from redactor.coordinator.bootstrap import prepare_run
    from redactor.formats.inspection import inspect_file
    from redactor.inference.model_loader import load_local_ner
    from redactor.persistence.files.artifacts import inspect_artifact
    from redactor.persistence.queue.tasks import claim_task
    from redactor.schemas.configuration import PipelineSettings
    from redactor.verification.native import verify_native
    from redactor.workers.handlers import pipeline_handlers
    from redactor.workers.pipeline import execute_task
    from redactor.workers.rewrite import rewrite_task

    inputs = tmp_path / "input"
    inputs.mkdir()
    source = inputs / "older.dcm"
    metadata = FileMetaDataset()
    metadata.TransferSyntaxUID = pydicom.uid.ExplicitVRLittleEndian
    metadata.MediaStorageSOPClassUID = pydicom.uid.SecondaryCaptureImageStorage
    metadata.MediaStorageSOPInstanceUID = pydicom.uid.UID("2.25.654321")
    dataset = FileDataset(str(source), {}, file_meta=metadata, preamble=bytes(128))
    dataset.SOPClassUID = metadata.MediaStorageSOPClassUID
    dataset.SOPInstanceUID = metadata.MediaStorageSOPInstanceUID
    dataset.PatientName = "Vale^Alina"
    dataset.PatientID = "78421"
    dataset.PatientBirthDate = "19360314"
    dataset.PatientAge = "090Y"
    dataset.StudyDate = "20260314"
    dataset.Modality = "OT"
    dataset.DeidentificationMethod = "basic"
    dataset.IssuerOfPatientID = "Harbor Clinic"
    related = Dataset()
    related.PatientID = dataset.PatientID
    related.IssuerOfPatientID = dataset.IssuerOfPatientID
    dataset.OtherPatientIDsSequence = [related]
    pydicom.dcmwrite(source, dataset, enforce_file_format=True)
    settings = PipelineSettings()
    key = bytes(range(32))
    ner = load_local_ner(settings.local)
    run = prepare_run(connection, inputs, settings, key)
    handlers = pipeline_handlers(settings, key, ner, run.resolution_task_id)
    while task := claim_task(connection):
        if task.step == "rewrite":
            break
        execute_task(connection, task, handlers)
    assert task is not None and task.step == "rewrite"
    result = rewrite_task(
        connection,
        task,
        settings=settings,
        mapping_key=key,
        local_ner=ner,
        resolution_task_id=run.resolution_task_id,
    )
    assert result.artifact is not None
    artifact = result.artifact
    inspection = inspect_file(source, settings.resources)
    checks = verify_native(
        connection,
        task,
        artifact,
        inspection,
        settings=settings,
        mapping_key=key,
        local_ner=ner,
        resolution_task_id=run.resolution_task_id,
    )
    assert all(check.status == "pass" for check in checks)
    saved = pydicom.dcmread(artifact.path)
    assert saved.PatientBirthDate == "" and saved.PatientAge == ""
    assert str(saved.StudyDate) != str(dataset.StudyDate)
    assert list(saved.DeidentificationMethod)[0] == "basic"
    assert saved.IssuerOfPatientID != dataset.IssuerOfPatientID
    assert saved.IssuerOfPatientID == saved.OtherPatientIDsSequence[0].IssuerOfPatientID
    assert all("19360314" not in method for method in saved.DeidentificationMethod)
    logical = read_dicom(artifact.path, settings.resources, extract_evidence=False)
    values = {record.locations[0]: record.values[0] for record in logical.records}
    assert values[("00101010",)] == "90+"
    assert values[("00100030",)].startswith("on or before ")
    with pytest.raises(ValueError):
        read_dicom(artifact.path, settings.resources)
    # A syntactically valid annotation is insufficient: its exact policy-derived
    # bound is independently recomputed from the original patient evidence.
    saved.DeidentificationMethod = [
        str(method).rsplit(" ", 1)[0] + " 2001"
        if "birth date on or before" in str(method)
        else method
        for method in saved.DeidentificationMethod
    ]
    pydicom.dcmwrite(artifact.path, saved, enforce_file_format=True)
    with pytest.raises(ValueError):
        verify_native(
            connection,
            task,
            inspect_artifact(artifact.path, persist=False),
            inspection,
            settings=settings,
            mapping_key=key,
            local_ner=ner,
            resolution_task_id=run.resolution_task_id,
        )
    saved.PatientBirthDate = "19360314"
    pydicom.dcmwrite(artifact.path, saved, enforce_file_format=True)
    with pytest.raises(ValueError):
        read_dicom(artifact.path, settings.resources, extract_evidence=False)
