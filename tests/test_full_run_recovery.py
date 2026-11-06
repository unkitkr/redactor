"""Compare clean executions with actual worker SIGKILL at durable boundaries."""

import base64
import csv
import json
import os
import sqlite3
import subprocess
import sys
from contextlib import closing
from pathlib import Path

from redactor.utils.constants import DATABASE_FILENAME


def test_complete_run_matches_clean_bytes_after_each_crash_boundary(
    tmp_path: Path,
) -> None:
    source = tmp_path / "input"
    source.mkdir()
    with (source / "records.csv").open("w", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(("patient", "mrn", "birth_date", "admit_ts", "dx_codes"))
        for day in range(1, 9):
            writer.writerow(
                ("Jane Smith", "001234", "1970-01-02", f"2026-01-{day:02d}", "E11.9")
            )
    (source / "nested.json").write_text(
        '{"name":"Jane Smith","mrn":"001234","birth_date":"1970-01-02",'
        '"encounter_date":"2026-01-02","glucose":1.2300000000000000001}'
    )
    (source / "corrupt.docx").write_bytes(b"PK\x03\x04 incomplete container")
    config = tmp_path / "config.toml"
    config.write_text("[resources]\ncheckpoint_records = 2\n")
    environment = dict(
        os.environ,
        REDACTOR_SECRET_KEY=base64.b64encode(bytes(range(32))).decode(),
        LLM_ENABLED="0",
    )
    hook_directory = Path(__file__).parent / "support/crash_boundary"
    expected: dict[str, bytes] | None = None
    boundaries = (
        "clean",
        "clean_repeat",
        "analysis_checkpoint",
        "analyze",
        "rewrite_checkpoint",
        "rewrite",
        "verify",
        "publish",
    )
    for boundary in boundaries:
        workspace = tmp_path / boundary
        workspace.mkdir()
        state = workspace / ".redactor"
        command = [
            sys.executable,
            "-m",
            "redactor",
            "--no-dashboard",
            "--input",
            str(source),
            "--state",
            str(state),
            "--config",
            str(config),
        ]
        if not boundary.startswith("clean"):
            marker = workspace / "crash-marker"
            injected = dict(
                environment,
                PYTHONPATH=str(hook_directory),
                REDACTOR_TEST_CRASH_BOUNDARY=boundary,
                REDACTOR_TEST_CRASH_MARKER=str(marker),
            )
            killed = subprocess.run(
                command, env=injected, capture_output=True, timeout=30
            )
            assert killed.returncode != 0, boundary
            assert marker.read_text() == boundary
            assert b'"exit_code":-9' in killed.stderr, killed.stderr

        completed = subprocess.run(
            command, env=environment, capture_output=True, timeout=30
        )
        assert completed.returncode == 0, (boundary, completed.stderr)
        output = workspace / "output"
        report = json.loads((output / "report.json").read_text())
        assert report["complete"] and report["published"] == 2, report
        assert report["quarantined"] == 1, report
        assert all(record["cost_bound_nanos"] == 0 for record in report["files"])
        actual = {
            path.relative_to(output / "published").as_posix(): path.read_bytes()
            for path in (output / "published").rglob("*")
            if path.is_file()
        }
        if expected is None:
            expected = actual
        assert actual == expected, boundary
        assert (output / "quarantine/corrupt.docx").read_bytes() == (
            source / "corrupt.docx"
        ).read_bytes()
        with closing(sqlite3.connect(state / DATABASE_FILENAME)) as connection:
            assert connection.execute("PRAGMA integrity_check").fetchone() == ("ok",)
            assert connection.execute(
                "SELECT count(*) FROM model_attempts"
            ).fetchone() == (0,)
            assert connection.execute(
                "SELECT count(*) FROM tasks WHERE status != 'succeeded'"
            ).fetchone() == (0,)
            assert (
                connection.execute(
                    "SELECT count(*) FROM attempts WHERE status = 'succeeded'"
                ).fetchone()
                == connection.execute("SELECT count(*) FROM tasks").fetchone()
            )
