"""Run the real multiprocess CLI, reconcile its outputs, and replay accepted work."""

import base64
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path


def test_clinical_cli_publishes_verifies_and_replays(tmp_path: Path) -> None:
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
    replay = subprocess.run(
        command, env=environment, capture_output=True, text=True, timeout=30
    )
    assert replay.returncode == 0, replay.stderr
    assert published.read_bytes() == before
    assert json.loads(report_path.read_text()) == report
    assert "private" not in report_path.read_text()
    assert all(item["cost_bound_nanos"] == 0 for item in report["files"])
