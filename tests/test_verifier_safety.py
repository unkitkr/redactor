"""Reject omitted evidence even when the inference boundary misses identifiers."""

import csv
from pathlib import Path

import pytest

from redactor.inference.model_loader import load_local_ner
from redactor.inference.text import find_text_phi
from redactor.policy.text import apply_text_edits, text_edits
from redactor.schemas.configuration import LocalSettings
from redactor.schemas.entities import TextEntity
from redactor.schemas.redaction import TextContext, TextEdit
from redactor.verification.text import verify_text_changes


def _miss_all_entities(_text: str) -> tuple[TextEntity, ...]:
    """An inference boundary can return no detections for identifying text."""
    return ()


def test_source_model_evidence_cannot_disappear_inside_a_partial_edit() -> None:
    original = "Review by O. Dacosta completed."
    mention = "O. Dacosta"

    def recognize_intact_name(text: str) -> tuple[TextEntity, ...]:
        if mention not in text:
            return ()
        start = text.index(mention)
        return (
            TextEntity(
                start=start,
                end=start + len(mention),
                text=mention,
                entity_type="person",
            ),
        )

    surname_start = original.index("Dacosta")
    partial = TextEdit(
        start=surname_start,
        end=surname_start + len("Dacosta"),
        original="Dacosta",
        replacement="Vale",
        kind="patient_name",
    )
    with pytest.raises(ValueError):
        verify_text_changes(
            original,
            apply_text_edits(original, (partial,)),
            (partial,),
            recognize_intact_name,
            free_text=True,
        )

    # A model may include a role, but adding an actual unedited name token is
    # never equivalent to adding a grammatical label.
    for prefix, suffix, accepted in (
        ("Daughter ", "", True),
        ("", " & son-in-law", True),
        ("", " Moreno", False),
        ("O. ", "", False),
    ):
        source = prefix + "Dacosta" + suffix
        edit = partial.model_copy(update={"start": len(prefix), "end": len(prefix) + 7})

        def overextended_model(text: str) -> tuple[TextEntity, ...]:
            return (
                TextEntity(start=0, end=len(text), text=text, entity_type="person"),
            )

        if accepted:
            verify_text_changes(
                source,
                apply_text_edits(source, (edit,)),
                (edit,),
                overextended_model,
                free_text=True,
            )
        else:
            with pytest.raises(ValueError):
                verify_text_changes(
                    source,
                    apply_text_edits(source, (edit,)),
                    (edit,),
                    overextended_model,
                    free_text=True,
                )


def test_known_names_and_labelled_values_survive_blind_model_checks() -> None:
    for original in (
        "Marin Delcourt returned for review.",
        "Delcourt, Marin returned for review.",
        "M. Delcourt returned for review.",
        "M Delcourt returned for review.",
        "Marin Delcourt 250 mg daily.",
    ):
        with pytest.raises(ValueError):
            verify_text_changes(
                original,
                original,
                (),
                _miss_all_entities,
                free_text=True,
                patient_name="Marin Delcourt",
            )

    provider = "Reviewed by Linnea Rossetti."
    with pytest.raises(ValueError):
        verify_text_changes(
            provider,
            provider,
            (),
            _miss_all_entities,
            free_text=True,
            provider_name="Linnea Rossetti",
        )

    for original in (
        "Patient: Anton Beller.",
        "Mother: Celia Voss.",
        "Facility: Silver Meadow Clinic.",
        "Patient: Delcourt 250 mg daily.",
        "Patient: A12.4.",
    ):
        with pytest.raises(ValueError):
            verify_text_changes(
                original, original, (), _miss_all_entities, free_text=True
            )


def test_contact_coverage_includes_international_numbers_extensions_and_ipv6() -> None:
    for original in (
        "Reach the clinic at +49 30 1234 5678.",
        "Phone: +33 (0)1 42 68 53 00.",
        "Network address: 2001:db8:53::27.",
        "IP: fe80::a2b:3c4d.",
    ):
        with pytest.raises(ValueError):
            verify_text_changes(
                original, original, (), _miss_all_entities, free_text=True
            )

    original = "Call 212-555-0179 ext. 42."
    main_number = "212-555-0179"
    start = original.index(main_number)
    partial = TextEdit(
        start=start,
        end=start + len(main_number),
        original=main_number,
        replacement="646-555-0126",
        kind="phone",
    )
    with pytest.raises(ValueError):
        verify_text_changes(
            original,
            apply_text_edits(original, (partial,)),
            (partial,),
            _miss_all_entities,
            free_text=True,
        )


def test_saved_age_rewrites_preserve_clinical_content(tmp_path: Path) -> None:
    ner = load_local_ner(LocalSettings())
    context = TextContext(context_key="age-regression", maximum_date_shift_days=365)
    clinical = "Metformin 850 mg BID. No Bell's palsy."
    cases = (
        (f"Patient is 89 years old. {clinical}", "89 years old"),
        (f"Patient is 90 years old. {clinical}", "90+ years old"),
        (f"Patient is 94 years old. {clinical}", "90+ years old"),
        (f"Patient is 90+ years old. {clinical}", "90+ years old"),
        ("Infant age 7 months.", "7 months"),
        ("Symptoms began 5 days ago.", "5 days"),
        ("Metformin 90 mg daily.", "90 mg"),
    )
    records: list[tuple[str, tuple[TextEdit, ...], str]] = []
    path = tmp_path / "age-results.csv"
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(("note",))
        for original, expected in cases:
            findings = find_text_phi(original, ner)
            edits = text_edits(findings, context, bytes(range(32)))
            writer.writerow((apply_text_edits(original, edits),))
            records.append((original, edits, expected))

    with path.open(encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream)
        for row, (original, edits, expected) in zip(reader, records, strict=True):
            output = row["note"]
            verify_text_changes(original, output, edits, ner, free_text=True)
            assert expected in output
            if clinical in original:
                assert clinical in output
                with pytest.raises(ValueError):
                    verify_text_changes(
                        original,
                        output.replace("850 mg", "950 mg"),
                        edits,
                        ner,
                        free_text=True,
                    )


def test_malformed_edit_boundaries_cannot_authorize_insertions() -> None:
    original = "abc"
    for start, end in ((0, 0), (3, 3), (4, 5), (2, 1)):
        edit = TextEdit(
            start=start,
            end=end,
            original=original[start:end],
            replacement="replacement",
            kind="identifier",
        )
        output = original[:start] + edit.replacement + original[end:]
        with pytest.raises(ValueError):
            verify_text_changes(
                original, output, (edit,), _miss_all_entities, free_text=False
            )
