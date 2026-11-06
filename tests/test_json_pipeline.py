"""Exercise nested native JSON, exact numbers, attachments and repeatable outputs."""

import base64
import csv
import json
import os
import subprocess
import sys
from decimal import Decimal
from pathlib import Path

import pytest

from redactor.formats.json_document import read_json_document
from redactor.schemas.configuration import ResourceSettings
from redactor.verification.json import check_json_surfaces


def test_json_native_round_trip_replay_and_saved_surface_checks(tmp_path: Path) -> None:
    source = tmp_path / "input"
    source.mkdir()
    attachment = base64.b64encode(
        b'{"ssn":"326-42-7814","dob":"1972-03-04","verified":true}'
    ).decode()
    original = source / "nested.json"
    original.write_text(
        '{"patients":[{"mrn":"74208",'
        '"name":{"given":["Amina","J"],"family":"Keller"},'
        '"birthDate":"1972-03-04","encounter_date":"2024-03-12",'
        '"provider":{"name":"Terry Jones","npi":"1234567893"},'
        '"address":{"line":["52 Hawthorn Road"],"city":"Westview",'
        '"state":"CA","postalCode":"94107"},'
        '"observations":[{"value":1.23000000000000000000000001e-4,"unit":"mg/dL"}],'
        '"attachments":[{"content_type":"application/json",'
        f'"encoding":"base64","data":"{attachment}"}}],'
        '"notes":"Patient Amina Keller attended. Glucose 120 mg/dL."}],'
        '"record_count":1,"confirmed":true,"optional":null,'
        '"last_login_ipv6":"2001:db8:1234::7"}'
    )
    (source / "same-person.csv").write_text(
        "patient,mrn,birth_date,encounter_date,attending,npi\n"
        "Amina J Keller,74208,1972-03-04,2024-03-12,Terry Jones,1234567893\n"
    )
    for name, payload in (
        ("duplicate.json", '{"phone":"415-555-0152","phone":"415-555-0153"}'),
        ("trailing.json", '{"value":1,}'),
        (
            "unknown-payload.json",
            '{"encoding":"base64","content_type":"application/octet-stream","data":"YWJj"}',
        ),
    ):
        (source / name).write_text(payload)
    settings = tmp_path / "settings.toml"
    settings.write_text('[local]\nner = "spacy"\n')
    environment = dict(
        os.environ,
        REDACTOR_SECRET_KEY=base64.b64encode(bytes(range(32))).decode(),
        LLM_ENABLED="0",
    )
    snapshots: list[dict[str, bytes]] = []
    for run_name in ("first", "first", "independent"):
        run = tmp_path / run_name
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "redactor",
                "--input",
                str(source),
                "--state",
                str(run / ".redactor"),
                "--config",
                str(settings),
                "--no-dashboard",
            ],
            env=environment,
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 0, result.stderr
        output = run / "output"
        report = json.loads((output / "report.json").read_text())
        assert report["published"] == 2 and report["quarantined"] == 3, report
        assert all(record["cost_bound_nanos"] == 0 for record in report["files"])
        snapshots.append(
            {path.name: path.read_bytes() for path in (output / "published").iterdir()}
        )
    assert snapshots[0] == snapshots[1] == snapshots[2]
    saved = tmp_path / "first/output/published/nested.json"
    raw = saved.read_text()
    assert "1.23000000000000000000000001e-4" in raw
    data = json.loads(raw, parse_float=Decimal)
    patient = data["patients"][0]
    with (tmp_path / "first/output/published/same-person.csv").open(
        newline=""
    ) as stream:
        row = next(csv.DictReader(stream))
    assert patient["mrn"] == row["mrn"]
    assert patient["birthDate"] == row["birth_date"]
    assert patient["encounter_date"] == row["encounter_date"]
    assert patient["name"]["given"][0] == row["patient"].split()[0]
    assert patient["name"]["family"] == row["patient"].split()[-1]
    nested = json.loads(base64.b64decode(patient["attachments"][0]["data"]))
    assert nested["dob"] == patient["birthDate"]
    assert nested["ssn"] != "326-42-7814" and nested["verified"] is True
    assert data["optional"] is None and data["confirmed"] is True
    assert data["last_login_ipv6"] != "2001:db8:1234::7"
    assert "Glucose 120 mg/dL." in patient["notes"]
    assert not any(
        value in raw for value in ("Amina", "Keller", "Hawthorn", "Westview")
    )
    resources = ResourceSettings()
    document = read_json_document(original, resources)
    check_json_surfaces(original, saved, document, resources)
    for index, corrupted in enumerate(
        (
            raw.replace('"confirmed":true', '"confirmed":false'),
            raw[:-1] + ',"unassessed":"Nolan Pierce"}',
            raw.replace('"optional":null', '"optional":0'),
        )
    ):
        assert corrupted != raw
        changed = tmp_path / f"changed-{index}.json"
        changed.write_text(corrupted)
        with pytest.raises(ValueError):
            check_json_surfaces(original, changed, document, resources)
