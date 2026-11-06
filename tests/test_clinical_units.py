"""Preserve compound units through the real pipeline and reject hidden free text."""

import base64
import csv
import json
import os
import subprocess
import sys
from pathlib import Path


def test_clinical_unit_round_trip_and_unassessed_annotations(tmp_path: Path) -> None:
    source = tmp_path / "input"
    source.mkdir()
    units = (
        "10*3/uL",
        "10^6/L",
        "mg/dL",
        "mm[Hg]",
        "mmHg",
        "mL/(kg.min)",
        "kg.m/s2",
        "µmol/L",
        "[IU]/mL",
        "%",
        "mL/min",
        "/uL",
    )
    with (source / "units.csv").open("w", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(("lab_value", "unit"))
        writer.writerows(("1.200", unit) for unit in units)
    for number, unit in enumerate(("ClaraMorrison", "mg{Clara Morrison}", "mg//L")):
        (source / f"invalid-{number}.csv").write_text(f"lab_value,unit\n1.200,{unit}\n")
    settings = tmp_path / "settings.toml"
    settings.write_text('[local]\nner = "spacy"\n')
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "redactor",
            "--input",
            str(source),
            "--state",
            str(tmp_path / ".redactor"),
            "--config",
            str(settings),
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
    output = tmp_path / "output"
    report = json.loads((output / "report.json").read_text())
    assert report["published"] == 1 and report["quarantined"] == 3, report
    with (output / "published/units.csv").open(newline="") as stream:
        rows = tuple(csv.DictReader(stream))
    assert tuple(row["unit"] for row in rows) == units
    assert all(row["lab_value"] == "1.200" for row in rows)
