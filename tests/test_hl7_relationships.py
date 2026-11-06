"""Coded relationships survive native publication but cannot carry hidden names."""

import base64
import json
import os
import subprocess
import sys
from pathlib import Path


def test_hl7_relationship_displays_are_checked_as_code_value_pairs(
    tmp_path: Path,
) -> None:
    source = tmp_path / "input"
    source.mkdir()
    message = (
        "MSH|^~\\&|Sender|Facility|Receiver|Target|202507231345||"
        "ADT^A01|CTRL001|P|2.5.1\r"
        "PID|1||M234^^^Issuer^MR||Morales^Celia||19720416|F\r"
        "NK1|1|Morales^Pia|{relationship}^HL70063\r"
    )
    for name, relationship in (
        ("valid", "MTH^Mother"),
        ("local-code", "DAU^Daughter"),
        ("mismatched", "MTH^Pia Morales"),
        ("extra-name", "MTH^Mother Pia Morales"),
    ):
        (source / f"{name}.hl7").write_bytes(
            message.format(relationship=relationship).encode()
        )
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
            str(tmp_path / ".redactor"),
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
    output = tmp_path / "output"
    report = json.loads((output / "report.json").read_text())
    assert report["published"] == report["quarantined"] == 2, report
    for name, relationship in (("valid", "MTH^Mother"), ("local-code", "DAU^Daughter")):
        saved = (output / "published" / f"{name}.hl7").read_bytes()
        assert relationship.encode() in saved
        assert b"Morales" not in saved and b"Celia" not in saved and b"Pia" not in saved
    for name in ("mismatched", "extra-name"):
        assert not (output / "published" / f"{name}.hl7").exists()
        assert (output / "quarantine" / f"{name}.hl7.reason.json").exists()
