"""Run unseen names and benign metadata through actual models and saved files."""

import base64
import csv
import json
import os
import re
import subprocess
import sys
from datetime import date, datetime
from pathlib import Path

import pytest


def test_local_pipeline_handles_context_without_title_or_person_allowlists(
    tmp_path: Path,
) -> None:
    repository = Path(__file__).parents[1]
    weights = repository / ".models/gliner-pii-edge-v1.0/onnx/model_quint8.onnx"
    if not weights.is_file():
        pytest.skip("Pinned GLiNER weights must be staged before integration testing")
    source = tmp_path / "input"
    source.mkdir()
    for name, text in (
        ("census.txt", "Census"),
        ("ledger.txt", "Ledger"),
        ("contact.txt", "Contact: 312-555-0193."),
    ):
        (source / name).write_text(text)
    with (source / "records.csv").open("w", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(
            ("patient", "mrn", "birth_date", "admit_ts", "dx_codes", "comments")
        )
        writer.writerow(
            (
                "Nadia Chen",
                "P900",
                "1975-04-18",
                "2025-07-23",
                "I10",
                "Chen returned. Friend Rowan Hale visited. No Bell's palsy. "
                "Metformin 850 mg BID. GCS 15. Call 312-555-0193. "
                "Return 07/24/25 13:45.",
            )
        )
    originals = {path.name: path.read_bytes() for path in source.iterdir()}
    environment = dict(
        os.environ,
        REDACTOR_SECRET_KEY=base64.b64encode(bytes(range(32))).decode(),
        LLM_ENABLED="0",
    )
    command = [
        sys.executable,
        "-m",
        "redactor",
        "--input",
        str(source),
        "--state",
        str(tmp_path / ".redactor"),
        "--config",
        str(repository / "redactor.toml"),
        "--no-dashboard",
    ]
    first = subprocess.run(
        command, env=environment, capture_output=True, text=True, timeout=45
    )
    assert first.returncode == 0, first.stderr
    output = tmp_path / "output"
    report = json.loads((output / "report.json").read_text())
    assert report["published"] == 4, report
    assert report["quarantined"] == 0
    published = output / "published"
    assert (published / "census.txt").read_text() == "Census"
    assert (published / "ledger.txt").read_text() == "Ledger"
    text = (published / "records.csv").read_text()
    for private in ("Nadia", "Chen", "Rowan", "Hale", "312-555-0193"):
        assert private not in text
    for clinical in (
        "I10",
        "Bell's palsy",
        "Metformin 850 mg BID",
        "GCS 15",
        "visited",
    ):
        assert clinical in text
    with (published / "records.csv").open(newline="") as stream:
        row = next(csv.DictReader(stream))
    appointment = re.search(r"Return ([0-9/]+) 13:45", row["comments"])
    assert appointment is not None
    assert (
        datetime.strptime(appointment[1], "%m/%d/%y").date()
        - date.fromisoformat(row["admit_ts"])
    ).days == 1
    assert "312-555-0193" not in (published / "contact.txt").read_text()
    accepted = {path.name: path.read_bytes() for path in published.iterdir()}
    replay = subprocess.run(
        command, env=environment, capture_output=True, text=True, timeout=45
    )
    assert replay.returncode == 0, replay.stderr
    assert {path.name: path.read_bytes() for path in published.iterdir()} == accepted
    assert json.loads((output / "report.json").read_text()) == report
    assert {path.name: path.read_bytes() for path in source.iterdir()} == originals
    assert all(file["cost_bound_nanos"] == 0 for file in report["files"])
