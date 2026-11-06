"""Keep native field context outside saved values and grounded edit ranges."""

import base64
import json
import os
import subprocess
import sys
from pathlib import Path

import pydicom
import pytest
from pydicom.dataset import FileDataset, FileMetaDataset

from redactor.formats.dicom import read_dicom, write_dicom
from redactor.inference.cache import cache_ner
from redactor.inference.context import contextual_ner
from redactor.inference.model_loader import load_local_ner
from redactor.inference.text import find_text_phi
from redactor.policy.text import apply_text_edits, text_edits
from redactor.schemas.configuration import LocalSettings, ResourceSettings
from redactor.schemas.entities import TextEntity
from redactor.schemas.redaction import TextContext
from redactor.utils.errors import (
    ERROR_COVERAGE,
    ERROR_ENTITY_EVIDENCE,
    ERROR_LOCAL_INPUT,
)
from redactor.verification.text import verify_text_changes


def test_dicom_context_preserves_clinical_values_and_redacts_identifiers(
    tmp_path: Path,
) -> None:
    repository = Path(__file__).parents[1]
    weights = repository / ".models/gliner-pii-edge-v1.0"
    if not (weights / "onnx/model_quint8.onnx").is_file():
        pytest.skip("Pinned GLiNER weights must be staged before integration testing")
    detector = load_local_ner(LocalSettings(ner="gliner", ner_directory=weights))
    verifier = load_local_ner(LocalSettings())
    inputs = tmp_path / "input"
    inputs.mkdir()
    for number, description in enumerate(
        (
            "CHEST 2 VIEWS",
            "Chest radiograph",
            "Chest radiograph. MRN ZX-7162",
            "Chest radiograph. MRN QV-3084",
        )
    ):
        source, output = (
            inputs / f"source-{number}.dcm",
            tmp_path / f"saved-{number}.dcm",
        )
        metadata = FileMetaDataset()
        metadata.TransferSyntaxUID = pydicom.uid.ExplicitVRLittleEndian
        metadata.MediaStorageSOPClassUID = pydicom.uid.SecondaryCaptureImageStorage
        metadata.MediaStorageSOPInstanceUID = pydicom.uid.UID(f"2.25.{number + 100}")
        dataset = FileDataset(str(source), {}, file_meta=metadata, preamble=bytes(128))
        dataset.SOPClassUID = metadata.MediaStorageSOPClassUID
        dataset.SOPInstanceUID = metadata.MediaStorageSOPInstanceUID
        dataset.StudyDescription = description
        pydicom.dcmwrite(source, dataset, enforce_file_format=True)
        document = read_dicom(source, ResourceSettings())
        record = next(
            item for item in document.records if item.locations == (("00081030",),)
        )
        assert record.field_labels == ("Study Description",)
        contextual = contextual_ner(
            detector, field_label=record.field_labels[0], maximum_characters=1000
        )
        if number == 0:
            # A label cannot authorize dropping an unresolved model observation.
            with pytest.raises(ValueError, match=ERROR_COVERAGE):
                find_text_phi(record.values[0], contextual)
            continue
        findings = find_text_phi(record.values[0], contextual)
        edits = text_edits(
            findings,
            TextContext(context_key="native-field", maximum_date_shift_days=365),
            bytes(range(32)),
        )
        value = apply_text_edits(description, edits)
        write_dicom(source, output, {record.locations[0]: value}, {})
        saved = read_dicom(output, ResourceSettings(), extract_evidence=False)
        written = next(
            item for item in saved.records if item.locations == record.locations
        )
        assert written.field_labels == record.field_labels
        assert written.values == (value,)
        if number == 1:
            assert value == description
        else:
            assert value.startswith("Chest radiograph. MRN ")
            assert description.split()[-1] not in value
        verify_text_changes(
            description,
            value,
            edits,
            contextual_ner(
                verifier, field_label=record.field_labels[0], maximum_characters=1000
            ),
            free_text=True,
        )
        with pytest.raises(ValueError):
            verify_text_changes(
                description, value + " altered", edits, verifier, free_text=True
            )
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "redactor",
            "--input",
            str(inputs),
            "--state",
            str(tmp_path / ".redactor"),
            "--config",
            str(repository / "redactor.toml"),
            "--no-dashboard",
        ],
        env=dict(
            os.environ,
            REDACTOR_SECRET_KEY=base64.b64encode(bytes(range(32))).decode(),
            LLM_ENABLED="0",
        ),
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    report = json.loads((tmp_path / "output/report.json").read_text())
    assert report["published"] == 3 and report["quarantined"] == 1
    for number in (1, 2, 3):
        published = pydicom.dcmread(tmp_path / f"output/published/source-{number}.dcm")
        assert str(published.StudyDescription).startswith("Chest radiograph")
        assert "ZX-7162" not in str(published.StudyDescription)
        assert "QV-3084" not in str(published.StudyDescription)


def test_context_cache_offsets_and_boundary_rejection_use_exact_source(
    tmp_path: Path,
) -> None:
    requests: list[str] = []

    def observe(text: str) -> tuple[TextEntity, ...]:
        requests.append(text)
        label, value = text.split(": ", 1)
        start = len(label) + 2
        return (
            TextEntity(start=0, end=len(label), text=label, entity_type="person"),
            TextEntity(start=start, end=len(text), text=value, entity_type="person"),
        )

    detector = cache_ner(observe, maximum_entries=8, maximum_text_characters=1000)
    first = contextual_ner(
        detector, field_label="Study Description", maximum_characters=1000
    )
    source = tmp_path / "value.txt"
    for value in ("Zoë Moreau", "Mateo Arora", "Zoë Moreau"):
        source.write_text(value)
        observed = first(source.read_text())
        assert observed == (
            TextEntity(start=0, end=len(value), text=value, entity_type="person"),
        )
    contextual_ner(detector, field_label="Series Description", maximum_characters=1000)(
        source.read_text()
    )
    assert len(requests) == 3
    assert requests[0].startswith("Study Description: ")
    assert requests[-1].startswith("Series Description: ")

    def crossing(text: str) -> tuple[TextEntity, ...]:
        end = text.index(": ") + 3
        return (TextEntity(start=0, end=end, text=text[:end], entity_type="person"),)

    with pytest.raises(ValueError, match=ERROR_ENTITY_EVIDENCE):
        contextual_ner(
            crossing, field_label="Study Description", maximum_characters=1000
        )(source.read_text())
    with pytest.raises(ValueError, match=ERROR_LOCAL_INPUT):
        contextual_ner(
            detector, field_label="Study Description", maximum_characters=20
        )(source.read_text())
