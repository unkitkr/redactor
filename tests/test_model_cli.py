"""Exercise configured model loading, publication, replay and failed loading."""

import base64
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from redactor.utils.errors import ERROR_LOCAL_UNAVAILABLE


def test_selected_gliner_publishes_replays_and_missing_weights_quarantine(
    tmp_path: Path,
) -> None:
    repository = Path(__file__).parents[1]
    weights = repository / ".models/gliner-pii-edge-v1.0/onnx/model_quint8.onnx"
    if not weights.is_file():
        pytest.skip("Pinned GLiNER weights must be staged before integration testing")
    source = tmp_path / "input"
    source.mkdir()
    original = (
        b"patient,mrn,birth_date,admit_ts,dx_codes,comments\n"
        b"Jane Smith,001234,1970-01-02,2026-01-02,E11.9,"
        b"Jane Smith returned for review.\n"
    )
    (source / "records.csv").write_bytes(original)
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
    ]
    first = subprocess.run(
        command, env=environment, capture_output=True, text=True, timeout=30
    )
    assert first.returncode == 0, first.stderr
    assert first.stdout == first.stderr == ""
    output = tmp_path / "output"
    report = json.loads((output / "report.json").read_text())
    assert report["complete"] and report["published"] == 1, report
    assert report["quarantined"] == 0
    published = (output / "published/records.csv").read_bytes()
    assert b"Jane Smith" not in published
    assert b"returned for review." in published
    assert b"E11.9" in published
    assert report["files"][0]["cost_bound_nanos"] == 0
    replay = subprocess.run(
        command, env=environment, capture_output=True, text=True, timeout=30
    )
    assert replay.returncode == 0, replay.stderr
    assert (output / "published/records.csv").read_bytes() == published
    assert json.loads((output / "report.json").read_text()) == report

    missing = tmp_path / "missing.toml"
    missing.write_text(
        '[local]\nner = "gliner"\nner_directory = "absent"\n[remote]\nenabled = false\n'
    )
    command[-1] = str(missing)
    command[command.index("--state") + 1] = str(tmp_path / "missing/.redactor")
    failed = subprocess.run(
        command, env=environment, capture_output=True, text=True, timeout=30
    )
    assert failed.returncode == 0, failed.stderr
    failed_output = tmp_path / "missing/output"
    failed_report = json.loads((failed_output / "report.json").read_text())
    assert failed_report["complete"] and failed_report["published"] == 0
    assert failed_report["quarantined"] == 1
    assert failed_report["files"][0]["reason"] == ERROR_LOCAL_UNAVAILABLE
    assert not list((failed_output / "published").glob("*.csv"))
    assert (source / "records.csv").read_bytes() == original
