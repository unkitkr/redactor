"""Keep prepared column lookup equivalent across saved, conflicting row evidence."""

import csv
from datetime import date
from pathlib import Path

import pytest

from redactor.identity.tabular import make_row_evidence, row_evidence
from redactor.schemas.redaction import ColumnPolicy, RowEvidence


def test_saved_row_evidence_preserves_context_conflicts_dates_and_age_boundary(
    tmp_path: Path,
) -> None:
    policies = (
        ColumnPolicy(index=0, kind="patient_name"),
        ColumnPolicy(index=1, kind="patient_name"),
        ColumnPolicy(index=2, kind="patient_id", namespace="mrn"),
        ColumnPolicy(index=3, kind="birth_date"),
        ColumnPolicy(index=4, kind="date"),
        ColumnPolicy(index=5, kind="date"),
        ColumnPolicy(index=6, kind="age"),
        ColumnPolicy(index=7, kind="text"),
        ColumnPolicy(index=8, kind="provider_name"),
        ColumnPolicy(index=9, kind="provider_id", namespace="npi"),
        ColumnPolicy(index=10, kind="clinical"),
    )
    first = (
        "Rowan Moss",
        " Rowan Moss ",
        "00-123",
        "1936-01-03",
        "2026-01-02T23:45:00-05:00",
        "01/03/2026 01:15:00+05:30",
        "89",
        "Glucose 106 mg/dL.",
        "Taylor Park",
        "1234567890",
        "106",
    )
    rows = (
        first,
        (*first[:6], "90", *first[7:]),
        ("", "Rowan Moss", "", "", "2026-01-03", "", "", "Age 90 years", "", "", ""),
        ("", " ", "", "", "2026-01-03", "", "", "", "Taylor Park", "", ""),
        ("", " ", "", "", "", "", "", "", "", "", ""),
    )
    source = tmp_path / "evidence.csv"
    with source.open("w", newline="") as stream:
        csv.writer(stream).writerows(rows)
    extract = make_row_evidence(policies, "source-digest")
    saved = tmp_path / "evidence.json"
    results = []
    with source.open(newline="") as stream:
        for number, cells in enumerate(csv.reader(stream), 1):
            values = tuple(cells)
            prepared = extract(values, number)
            assert prepared == row_evidence(values, policies, "source-digest", number)
            saved.write_text(prepared.model_dump_json())
            results.append(RowEvidence.model_validate_json(saved.read_text()))
    patient = results[0].patient
    assert patient is not None
    assert patient.identifier == "00123" and patient.identifier_namespace == "mrn"
    assert patient.birth_date == date(1936, 1, 3)
    assert patient.reference_date == date(2026, 1, 3)
    assert not patient.explicit_older_age
    for result in results[1:3]:
        assert result.patient is not None and result.patient.explicit_older_age
        assert result.patient.context_key != patient.context_key
    assert results[3].patient is None and results[3].provider is not None
    assert results[4] == RowEvidence(patient=None, provider=None)
    assert extract(first, 99).patient != patient
    failures = (
        ("Different Person", *first[1:]),
        (*first[:4], "2026-01-02T25:00Z", *first[5:]),
        (*first[:6], "90 years", *first[7:]),
    )
    for values in failures:
        with pytest.raises(ValueError) as serial:
            row_evidence(values, policies, "source-digest", 1)
        with pytest.raises(ValueError) as prepared_error:
            extract(values, 1)
        assert str(prepared_error.value) == str(serial.value)
    with pytest.raises(IndexError):
        extract(first[:-1], 1)
