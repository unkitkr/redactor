"""Clinical free text retains measurements and medication names after native I/O."""

import csv
from datetime import date
from pathlib import Path

import pytest

from redactor.formats.tabular_fields import column_policies, validate_clinical_field
from redactor.identity.tabular import row_evidence
from redactor.inference.model_loader import load_local_ner
from redactor.inference.text import find_text_phi
from redactor.policy.text import apply_text_edits, text_edits
from redactor.schemas.configuration import LocalSettings
from redactor.schemas.entities import TextEntity
from redactor.schemas.redaction import TextContext, TextRange
from redactor.utils.errors import ERROR_CLINICAL_CHANGED
from redactor.verification.text import scan_residuals, verify_text_changes


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


def test_written_ages_and_named_dates_are_verified_without_reaging_patient() -> None:
    ner = load_local_ner(LocalSettings())
    context = TextContext(context_key="calendar-record", maximum_date_shift_days=365)
    for original in (
        "The ninety-one-year-old patient returned on 29-Feb-2024.",
        "Age 91+. Follow-up March 1, 2024.",
        "Age 90+. Follow-up 01-Mar-2024.",
    ):
        findings = find_text_phi(original, ner)
        edits = text_edits(findings, context, bytes(range(32)))
        output = apply_text_edits(original, edits)
        verify_text_changes(original, output, edits, ner, free_text=True)
        assert "90+" in output and "90++" not in output
        assert "ninety-one" not in output and "91+" not in output
    policies = column_policies(("patient", "birth_date", "comments"))
    evidence = row_evidence(
        ("Jane Smith", "1970-01-01", "Mother: age 95. Patient is 56."),
        policies,
        "a" * 64,
        1,
    )
    assert evidence.patient is not None
    assert not evidence.patient.explicit_older_age


def test_verifier_does_not_exempt_a_sensitive_value_from_partial_overlap() -> None:
    ner = load_local_ner(LocalSettings())
    for text, start, end in (
        ("jane.smith@example.test", 0, 4),
        ("MRN 123456789", 4, 8),
        ("daughter Jane Smith", 9, 13),
    ):
        with pytest.raises(ValueError, match="residual_phi_detected"):
            scan_residuals(text, (TextRange(start=start, end=end),), ner)


@pytest.mark.parametrize(
    ("place", "suffix"),
    (
        ("Cedarvale", "General Hospital"),
        ("Riverton", "Clinic"),
        ("Elmridge", "Medical Centre"),
    ),
)
def test_grounded_facility_span_covers_full_name_without_crossing_lines(
    tmp_path: Path,
    place: str,
    suffix: str,
) -> None:
    facility = f"{place} {suffix}"
    original = f"Signed | {facility} | Glucose 106 mg/dL."
    context = TextContext(context_key="facility-record", maximum_date_shift_days=365)

    def partial_location(text: str) -> tuple[TextEntity, ...]:
        start = text.index(place)
        return (
            TextEntity(
                start=start, end=start + len(place), text=place, entity_type="location"
            ),
        )

    findings = find_text_phi(original, partial_location)
    assert len(findings) == 1 and findings[0].original == facility
    assert findings[0].kind == "organization"
    for reversed_order in (False, True):

        def split_facility(
            text: str, reverse: bool = reversed_order
        ) -> tuple[TextEntity, ...]:
            first = partial_location(text)[0]
            start = text.index(suffix)
            second = TextEntity(
                start=start,
                end=start + len(suffix),
                text=suffix,
                entity_type="organization",
            )
            return (second, first) if reverse else (first, second)

        assert find_text_phi(original, split_facility) == findings

    def extended_facility(text: str) -> tuple[TextEntity, ...]:
        first = partial_location(text)[0]
        start = text.index(suffix)
        return (
            first,
            TextEntity(
                start=start,
                end=len(text),
                text=text[start:],
                entity_type="organization",
            ),
        )

    with pytest.raises(ValueError, match="invalid_entity_span_evidence"):
        find_text_phi(facility + " Alina Calder", extended_facility)
    edits = text_edits(findings, context, bytes(range(32)))
    saved = tmp_path / "facility.txt"
    saved.write_text(apply_text_edits(original, edits))
    ner = load_local_ner(LocalSettings())
    verify_text_changes(original, saved.read_text(), edits, ner, free_text=True)
    assert (
        facility not in saved.read_text() and "Glucose 106 mg/dL." in saved.read_text()
    )
    with pytest.raises(ValueError, match="expected_replacement_missing"):
        verify_text_changes(original, original, edits, ner, free_text=True)
    with pytest.raises(ValueError, match="clinical_content_changed"):
        verify_text_changes(
            original,
            saved.read_text().replace("106", "109"),
            edits,
            ner,
            free_text=True,
        )
    separated = f"{place}\n{suffix}\nGlucose 106 mg/dL."
    separate = find_text_phi(separated, partial_location)
    assert separate[0].original == place and separate[0].kind == "location"


def test_title_only_person_predictions_preserve_titles_and_detect_names(
    tmp_path: Path,
) -> None:
    def whole_person(text: str) -> tuple[TextEntity, ...]:
        return (TextEntity(start=0, end=len(text), text=text, entity_type="person"),)

    saved = tmp_path / "title.txt"
    for title in ("Dr.", "Professor", "Mr", "Ms."):
        assert not find_text_phi(title, whole_person)
        saved.write_text(title)
        verify_text_changes(title, saved.read_text(), (), whole_person, free_text=True)
        name = f"{title} Alina Calder"
        assert find_text_phi(name, whole_person)
        saved.write_text(name)
        with pytest.raises(ValueError, match="residual_phi_detected"):
            verify_text_changes(
                name, saved.read_text(), (), whole_person, free_text=True
            )
    for name in ("Drake", "Missouri", "Professorx"):
        assert find_text_phi(name, whole_person)
        with pytest.raises(ValueError, match="residual_phi_detected"):
            verify_text_changes(name, name, (), whole_person, free_text=True)


@pytest.mark.parametrize("score", ("3", "score: 9/15", "= 15"))
def test_spelled_out_clinical_score_keeps_its_name_and_numeric_value(
    tmp_path: Path,
    score: str,
) -> None:
    original = f"Glasgow Coma Scale {score}"

    def city_prediction(text: str) -> tuple[TextEntity, ...]:
        start = text.index("Glasgow")
        return (
            TextEntity(
                start=start, end=start + 7, text="Glasgow", entity_type="location"
            ),
        )

    def full_prediction(text: str) -> tuple[TextEntity, ...]:
        return (TextEntity(start=0, end=len(text), text=text, entity_type="person"),)

    assert not find_text_phi(original, city_prediction)
    saved = tmp_path / "score.txt"
    saved.write_text(original)
    verify_text_changes(
        original, saved.read_text(), (), full_prediction, free_text=True
    )
    for altered in (original.replace("Glasgow", "Elsewhere"), original + " Amina"):
        saved.write_text(altered)
        with pytest.raises(ValueError, match="clinical_content_changed"):
            verify_text_changes(
                original, saved.read_text(), (), full_prediction, free_text=True
            )
    assert find_text_phi("Glasgow", city_prediction)
    assert not find_text_phi("Glasgow Coma Scale", city_prediction)
    for ungrounded in ("Glasgow", "Glasgow Coma Scale Amina", "Glasgow Coma Scale 16"):
        with pytest.raises(ValueError, match="residual_phi_detected"):
            verify_text_changes(
                ungrounded, ungrounded, (), full_prediction, free_text=True
            )
