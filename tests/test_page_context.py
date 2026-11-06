"""Bound PDF context to its page and reconstruct it from independently saved text."""

import base64
import json
import os
import subprocess
import sys
from pathlib import Path

import pymupdf
import pytest

from redactor.formats.pdf import read_pdf
from redactor.inference.context import record_ner
from redactor.schemas.configuration import ResourceSettings
from redactor.schemas.entities import TextEntity
from redactor.schemas.native import NativeTextContext
from redactor.schemas.redaction import TextRange
from redactor.utils.errors import ERROR_ENTITY_EVIDENCE


def test_pdf_page_context_roundtrip_keeps_patients_separate(tmp_path: Path) -> None:
    repository = Path(__file__).parents[1]
    if not (
        repository / ".models/gliner-pii-edge-v1.0/onnx/model_quint8.onnx"
    ).is_file():
        pytest.skip("Pinned GLiNER weights must be staged before integration testing")
    inputs = tmp_path / "input"
    inputs.mkdir()
    source = inputs / "clinical.pdf"
    with pymupdf.open() as pdf:
        for name, identifier in (("Alina Vale", "PV-7041"), ("Mateo Zuri", "FZ-2846")):
            page = pdf.new_page()
            for index, line in enumerate(
                (
                    f"Patient: {name}",
                    f"MRN: {identifier}",
                    "Assessment: Type 2 diabetes mellitus. A1c 7.3%.",
                    "Follow-up 03/14/2026.",
                )
            ):
                page.insert_text((50, 60 + 20 * index), line)
        pdf.save(source)
    original = read_pdf(source, ResourceSettings())
    for record in original.records:
        if record.text_context is None:
            continue
        assert len(record.text_context.text) <= 1024
        assert ("Alina Vale" in record.text_context.text) != (
            "Mateo Zuri" in record.text_context.text
        )
        for value, span in zip(record.values, record.text_context.ranges, strict=True):
            assert record.text_context.text[span.start : span.end] == value
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
            LLM_ENABLED="0",
            REDACTOR_SECRET_KEY=base64.b64encode(bytes(range(32))).decode(),
        ),
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    report = json.loads((tmp_path / "output/report.json").read_text())
    assert report["published"] == 1 and report["quarantined"] == 0, report
    saved = read_pdf(
        tmp_path / "output/published/clinical.pdf",
        ResourceSettings(),
        extract_evidence=False,
    )
    contexts = [
        record.text_context.text for record in saved.records if record.text_context
    ]
    assert contexts
    assert all(
        "Alina Vale" not in text and "Mateo Zuri" not in text for text in contexts
    )
    assert all("PV-7041" not in text and "FZ-2846" not in text for text in contexts)
    assert all("Type 2 diabetes mellitus. A1c 7.3%." in text for text in contexts)


def test_pdf_context_requires_anchor_and_rejects_bad_projection(tmp_path: Path) -> None:
    source = tmp_path / "source.pdf"
    with pymupdf.open() as pdf:
        for lines in (
            ("Patient: Alina Vale", "MRN: PV-7041", "Clinical note."),
            ("Patient: Mateo Zuri", "Clinical note."),
            ("Patient: Alina Vale", "Patient: Mateo Zuri", "MRN: PV-7041"),
            (
                "Patient: Alina Vale",
                "MRN: PV-7041",
                *(
                    "Routine clinical assessment and laboratory followup."
                    for _ in range(28)
                ),
            ),
        ):
            page = pdf.new_page()
            for index, line in enumerate(lines):
                page.insert_text((50, 60 + 20 * index), line)
        pdf.save(source)
    document = read_pdf(source, ResourceSettings(), extract_evidence=False)
    records = [record for record in document.records if record.text_context]
    assert records and all(
        record.locations[0][0].startswith("pdf-page:0:") for record in records
    )
    record = records[0]
    context = record.text_context
    assert context is not None
    value = record.values[0]
    target = context.ranges[0]

    def crossing(text: str) -> tuple[TextEntity, ...]:
        stop = target.start + len(value) + 1
        return (
            TextEntity(
                start=target.start,
                end=stop,
                text=text[target.start : stop],
                entity_type="person",
            ),
        )

    with pytest.raises(ValueError, match=ERROR_ENTITY_EVIDENCE):
        record_ner(crossing, record, 0, 2048)(value)
    corrupted = record.model_copy(
        update={
            "text_context": NativeTextContext(
                text=context.text,
                ranges=(TextRange(start=1, end=2), *context.ranges[1:]),
            )
        }
    )
    with pytest.raises(ValueError, match=ERROR_ENTITY_EVIDENCE):
        record_ner(crossing, corrupted, 0, 2048)
