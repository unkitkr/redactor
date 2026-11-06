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
    assert report["inventoried"] == 2
    assert report["published"] == 1, report
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
