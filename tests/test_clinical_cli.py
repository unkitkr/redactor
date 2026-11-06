"""Run the real multiprocess CLI, reconcile its outputs, and replay accepted work."""

import base64
import csv
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from redactor.policy.normalization import normalize_name


def test_clinical_cli_publishes_verifies_and_replays(tmp_path: Path) -> None:
    # This cross-format regression exercises the established spaCy path. Model
    # selection has its own integration test, with the checked-in configuration.
    configuration = tmp_path / "spacy.toml"
    configuration.write_text('[local]\nner = "spacy"\n[remote]\nenabled = false\n')
    source = tmp_path / "input"
    source.mkdir()
    fixtures = Path(__file__).parents[1] / "input"
    shutil.copyfile(fixtures / "encounters.csv", source / "records.csv")
    shutil.copyfile(fixtures / "billing_export.csv", source / "mislabeled.csv")
    shutil.copyfile(fixtures / "adt_a01.hl7", source / "message.hl7")
    (source / "note.txt").write_text(
        "Patient: Smith, Jane    MRN: 123-456\r\n"
        "DOB: 01/02/1970    Admit: 29-Feb-2024\r\n"
        "Attending: Terry Jones, MD (NPI 1234567893)\r\n"
        "Creatinine 1.1 mg/dL. Room 412-B. Portal 73.167.18.52.\r\n"
        "SSN 526-42-1497. Contact jane@example.test.\r\n",
        encoding="cp1252",
        newline="",
    )
    (source / "broken.docx").write_bytes(b"PK\x03\x04 incomplete private archive")
    environment = dict(os.environ)
    environment["REDACTOR_SECRET_KEY"] = base64.b64encode(bytes(range(32))).decode()
    environment["LLM_ENABLED"] = "0"
    command = [
        sys.executable,
        "-m",
        "redactor",
        "--input",
        str(source),
        "--state",
        str(tmp_path / ".redactor"),
        "--config",
        str(configuration),
    ]
    first = subprocess.run(
        command, env=environment, capture_output=True, text=True, timeout=30
    )
    assert first.returncode == 0, first.stderr
    assert first.stdout == first.stderr == ""
    report_path = tmp_path / "output" / "report.json"
    report = json.loads(report_path.read_text())
    assert report["complete"] is True
    assert report["inventoried"] == 5
    assert report["published"] == 4, report
    assert report["quarantined"] == 1
    published = tmp_path / "output" / "published" / "records.csv"
    before = published.read_bytes()
    assert before != (source / "records.csv").read_bytes()
    with published.open(encoding="utf-8-sig", newline="") as stream:
        csv_rows = list(csv.DictReader(stream))
    with (source / "records.csv").open(encoding="utf-8-sig", newline="") as stream:
        source_rows = list(csv.DictReader(stream))
    matching_row = next(
        index for index, row in enumerate(source_rows) if row["mrn"] == "0087482"
    )
    hl7 = (tmp_path / "output/published/message.hl7").read_text()
    patient_segment = next(line for line in hl7.splitlines() if line.startswith("PID|"))
    patient_fields = patient_segment.split("|")
    assert normalize_name(patient_fields[5].replace("$", "^")) == normalize_name(
        csv_rows[matching_row]["patient"]
    )
    assert patient_fields[3].split("$")[0] == csv_rows[matching_row]["mrn"]
    replay = subprocess.run(
        command, env=environment, capture_output=True, text=True, timeout=30
    )
    assert replay.returncode == 0, replay.stderr
    assert published.read_bytes() == before
    assert json.loads(report_path.read_text()) == report
    assert "private" not in report_path.read_text()
    assert all(item["cost_bound_nanos"] == 0 for item in report["files"])
