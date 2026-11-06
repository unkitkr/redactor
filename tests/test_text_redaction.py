"""Clinical free text retains measurements and medication names after native I/O."""

import csv
from datetime import date
from pathlib import Path

import pytest

from redactor.formats.tabular_fields import column_policies, validate_clinical_field
from redactor.identity.tabular import row_evidence
from redactor.inference.ner import load_local_ner
from redactor.inference.text import find_text_phi
from redactor.policy.text import apply_text_edits, text_edits
from redactor.schemas.configuration import LocalSettings
from redactor.schemas.redaction import TextContext
from redactor.utils.errors import ERROR_CLINICAL_CHANGED


def test_text_patterns_and_local_ner_preserve_clinical_content(tmp_path: Path) -> None:
    texts = (
        'Pt states "better".\nDaughter Léa Smith (415-555-0104) to drive home; '
        "A1c 8.4%, metformin 1000 mg BID resumed.",
        "Age 91. Lives with husband Leonard at 912 Lantern Hill Road, Pine Ridge.\n"
        "No Bell's palsy. GCS 15.",
        "Albuterol MDI refilled, 90 mcg 2 puffs PRN.",
        "Atorvastatin 40 mg daily, LDL 92 mg/dL.",
        "Parkinson's disease, carbidopa-levodopa 25/100 TID. "
        "Neuro f/u w/ Dr. Desai on 06/23/2026.",
    )
    ner = load_local_ner(LocalSettings())
    context = TextContext(context_key="test-record", maximum_date_shift_days=365)
    output = tmp_path / "notes.csv"
    with output.open("w", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(("notes",))
        for text in texts:
            findings = find_text_phi(text, ner)
            writer.writerow(
                (
                    apply_text_edits(
                        text, text_edits(findings, context, bytes(range(32)))
                    ),
                )
            )
    with output.open(newline="") as stream:
        actual = [row["notes"] for row in csv.DictReader(stream)]
    for protected in (
        "A1c 8.4%",
        "metformin 1000 mg BID",
        "Bell's palsy",
        "GCS 15",
        "Atorvastatin 40 mg daily",
        "LDL 92 mg/dL",
        "Parkinson's disease",
        "carbidopa-levodopa 25/100 TID",
    ):
        assert protected in "\n".join(actual)
    assert actual[2] == texts[2]
    assert actual[3] == texts[3]
    for private in (
        "Léa Smith",
        "415-555-0104",
        "Leonard",
        "Lantern Hill",
        "Pine Ridge",
        "Desai",
        "06/23/2026",
    ):
        assert private not in "\n".join(actual)
    assert "Age 90+." in actual[1]


def test_tabular_identity_uses_headers_and_keeps_clinical_codes_distinct(
    tmp_path: Path,
) -> None:
    source = tmp_path / "reordered.csv"
    source.write_text(
        "dx_codes,patient,attending_npi,mrn,birth_date,admit_ts,comments,attending\n"
        'E11.9;I10,"Smith, Jane",1234567893,001-234,01/02/1936,2026-01-02,'
        "Age 90.,Dr. Terry Jones\n"
    )
    with source.open(newline="") as stream:
        reader = csv.reader(stream)
        policies = column_policies(tuple(next(reader)))
        values = tuple(next(reader))
    evidence = row_evidence(values, policies, "a" * 64, 1)
    assert evidence.patient is not None and evidence.provider is not None
    assert evidence.patient.identifier == "001234"
    assert evidence.patient.birth_date == date(1936, 1, 2)
    assert evidence.patient.reference_date == date(2026, 1, 2)
    assert evidence.patient.explicit_older_age
    assert evidence.provider.role == "provider"
    validate_clinical_field(values[0], policies[0].namespace)
    with pytest.raises(ValueError, match=ERROR_CLINICAL_CHANGED):
        validate_clinical_field("E11.9; Jane Smith", policies[0].namespace)
