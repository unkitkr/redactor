"""Direct native round trips, no infrastructure, and corrupted saved artifacts."""

import csv
import json
import sqlite3
from pathlib import Path

import pytest
from openpyxl import Workbook, load_workbook

from redactor.inference.runtime import runtime_adapters
from redactor.schemas.configuration import PipelineSettings
from simple_pipeline.content import extract_file, save_file
from simple_pipeline.identity import resolve_identities
from simple_pipeline.redact import analyze_file, redact_file
from simple_pipeline.run import run
from simple_pipeline.verify import verify_saved


def test_direct_run_preserves_native_content_without_database(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def forbidden_database(*args: object, **kwargs: object) -> None:
        raise AssertionError("The direct experiment must not open SQLite")

    monkeypatch.setattr(sqlite3, "connect", forbidden_database)
    source = tmp_path / "input"
    source.mkdir()
    columns = ("patient", "mrn", "birth_date", "encounter_date", "value", "unit")
    values = ("Nadia Velez", "90123", "1934-03-12", "2024-03-12", "120", "mg/dL")
    (source / "record.csv").write_text(
        ",".join(columns) + "\n" + ",".join(values) + "\n"
    )
    (source / "record.json").write_text(
        json.dumps(dict(zip(columns, values, strict=True)))
    )
    workbook = Workbook()
    sheet = workbook.active
    assert sheet is not None
    sheet.append(columns)
    sheet.append(values)
    workbook.save(source / "mislabeled.csv")
    workbook.close()
    (source / "broken.docx").write_bytes(b"PK\x03\x04not a zip archive")
    settings = PipelineSettings()
    detector, ocr, verifier = runtime_adapters(settings.local, settings.resources)
    snapshots: list[dict[str, bytes]] = []
    for run_name in ("first", "second"):
        output = tmp_path / run_name
        results = run(
            source, output, settings, bytes(range(32)), detector, ocr, verifier
        )
        assert sum(item.status == "published" for item in results) == 3, results
        failure = next(item for item in results if item.status == "quarantined")
        assert failure.input == "broken.docx"
        assert failure.reason == "invalid_container_structure"
        report = json.loads((output / "report.json").read_text())
        assert report["remote_calls"] == 0 and report["durability"] is False
        assert not list(output.rglob("*.sqlite*"))
        snapshots.append(
            {path.name: path.read_bytes() for path in (output / "published").iterdir()}
        )
    assert snapshots[0] == snapshots[1]
    output = tmp_path / "first/published"
    with (output / "record.csv").open(newline="") as stream:
        saved_csv = next(csv.DictReader(stream))
    saved_json = json.loads((output / "record.json").read_text())
    with (output / "mislabeled.csv").open("rb") as workbook_stream:
        saved_book = load_workbook(workbook_stream)
        saved_xlsx = dict(
            zip(columns, tuple(saved_book.worksheets[0].values)[1], strict=True)
        )
        saved_book.close()
    assert saved_csv == saved_json == saved_xlsx
    assert saved_csv["patient"] != values[0]
    assert saved_csv["mrn"] != values[1]
    assert saved_csv["birth_date"].startswith("on or before ")
    assert saved_csv["value"] == "120" and saved_csv["unit"] == "mg/dL"
    with pytest.raises(FileExistsError):
        run(
            source,
            tmp_path / "first",
            settings,
            bytes(range(32)),
            detector,
            ocr,
            verifier,
        )


def test_direct_verifier_rejects_corrupted_saved_bytes_and_omitted_edits(
    tmp_path: Path,
) -> None:
    original = tmp_path / "records.csv"
    original.write_text(
        "patient,mrn,birth_date,encounter_date,comments\n"
        'Nadia Velez,90123,1974-03-12,2024-03-12,"Glucose 120 mg/dL.\n'
        'Phone 415-555-0149."\n'
    )
    settings = PipelineSettings()
    detector, ocr, verifier = runtime_adapters(settings.local, settings.resources)
    source = extract_file(original, settings)
    analysis = analyze_file(source, settings, detector, ocr)
    lookup = resolve_identities((analysis,), bytes(range(32)), 365)
    plan = redact_file(analysis, lookup, bytes(range(32)), settings)
    saved = tmp_path / "saved.csv"
    save_file(plan, saved, settings)
    verify_saved(plan, saved, settings, verifier, bytes(range(32)))
    clean = saved.read_bytes()
    for corrupted in (
        clean.replace(b"120 mg/dL", b"121 mg/dL"),
        clean.splitlines(keepends=True)[0],
        clean + clean[clean.index(b"\n") + 1 :],
        original.read_bytes(),
    ):
        saved.write_bytes(corrupted)
        with pytest.raises(ValueError):
            verify_saved(plan, saved, settings, verifier, bytes(range(32)))
    # Even when the writer omits a free-text edit, the independent source scan
    # must catch the phone number instead of trusting an empty edit list.
    row_edits = (*plan.edits[0][:-1], ())
    incomplete = plan.model_copy(update={"edits": (row_edits,)})
    save_file(incomplete, saved, settings)
    with pytest.raises(ValueError, match="residual_phi_detected"):
        verify_saved(incomplete, saved, settings, verifier, bytes(range(32)))
    missing_name = plan.model_copy(update={"edits": (((), *plan.edits[0][1:]),)})
    save_file(missing_name, saved, settings)
    with pytest.raises(ValueError):
        verify_saved(missing_name, saved, settings, verifier, bytes(range(32)))
