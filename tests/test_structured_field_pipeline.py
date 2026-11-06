"""Validate structured metadata and clinical values across saved native files."""

import base64
import json
import os
import subprocess
import sys
from pathlib import Path

from openpyxl import Workbook, load_workbook


def test_structured_policies_preserve_clinical_values_and_reject_bad_versions(
    tmp_path: Path,
) -> None:
    source = tmp_path / "input"
    source.mkdir()
    record = {
        "schema": "v1.3",
        "schema_version": "2.0",
        "version": "3",
        "payer": "Northbridge Health Insurance",
        "organization": "Lakeside Research Clinic",
        "test": "Hemoglobin A1c",
        "value": 7.2,
        "unit": "%",
    }
    (source / "record.json").write_text(json.dumps(record))
    (source / "invalid-version.json").write_text(
        json.dumps({**record, "schema_version": "2.0-private-patient"})
    )
    workbook = Workbook()
    sheet = workbook.active
    assert sheet is not None
    sheet.title = "Results"
    sheet.append(list(record))
    sheet.append(list(record.values()))
    workbook.save(source / "record.xlsx")
    workbook.close()
    config = tmp_path / "settings.toml"
    config.write_text('[local]\nner = "spacy"\n')
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "redactor",
            "--input",
            str(source),
            "--state",
            str(tmp_path / "run/.redactor"),
            "--config",
            str(config),
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
    output = tmp_path / "run/output"
    report = json.loads((output / "report.json").read_text())
    assert report["published"] == 2 and report["quarantined"] == 1, report
    assert [
        entry["reason"] for entry in report["files"] if entry["status"] == "quarantined"
    ] == ["clinical_content_changed"]
    saved_json = json.loads((output / "published/record.json").read_text())
    saved_workbook = load_workbook(output / "published/record.xlsx", data_only=False)
    saved_sheet = saved_workbook.worksheets[0]
    saved_xlsx = dict(zip(record, (cell.value for cell in saved_sheet[2]), strict=True))
    saved_workbook.close()
    for saved in (saved_json, saved_xlsx):
        for field in ("schema", "schema_version", "version", "test", "value", "unit"):
            assert saved[field] == record[field]
        for field in ("payer", "organization"):
            assert saved[field] and saved[field] != record[field]
            assert saved[field] == saved_json[field]
    assert not (output / "published/invalid-version.json").exists()
