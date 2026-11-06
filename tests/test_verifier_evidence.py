"""Exercise independent source evidence against omitted and partial rewrites."""

import pytest

from redactor.inference.text import find_text_phi
from redactor.policy.text import apply_text_edits
from redactor.schemas.entities import TextEntity
from redactor.schemas.redaction import TextEdit
from redactor.verification.evidence import known_name_ranges
from redactor.verification.text import verify_text_changes


def _miss_all_entities(_text: str) -> tuple[TextEntity, ...]:
    return ()


def test_long_contact_candidates_and_explicit_prefixes_fail_closed() -> None:
    for prefix in ("+", "00", ""):
        for digits in ("493055501276", "493055501276123456", "4930555012761234567890"):
            original = f"Call {prefix}{digits} for an appointment."
            with pytest.raises(ValueError):
                verify_text_changes(
                    original, original, (), _miss_all_entities, free_text=True
                )

    for prefix in ("+", "00"):
        original = f"Recorded {prefix}493055501276 mg."
        with pytest.raises(ValueError):
            verify_text_changes(
                original, original, (), _miss_all_entities, free_text=True
            )

    # Long measured values and ordinary signed decimals have typed clinical
    # evidence. Neither a digit count nor a leading sign alone makes them PHI.
    for original in (
        "Concentration 12345678 mg/dL.",
        "Measured change +1234.5678 mg/dL.",
        "Measured change -1234.5678 mg/dL.",
        "Measured change +0.00123456 mmol/L.",
    ):
        verify_text_changes(original, original, (), _miss_all_entities, free_text=True)


def test_extensions_cannot_be_left_outside_phone_edits() -> None:
    number = "415-555-0128"
    for extension in (
        " ext. 93",
        " EXT:93",
        " ext=93",
        " extension: 93",
        " x=93",
        " # 93",
        " ext:12345678901",
    ):
        original = f"Call {number}{extension}."
        findings = find_text_phi(original, _miss_all_entities)
        assert len(findings) == 1
        assert findings[0].original == number + extension
        start = original.index(number)
        partial = TextEdit(
            start=start,
            end=start + len(number),
            original=number,
            replacement="503-555-0176",
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


def test_corroborated_apostrophe_spellings_preserve_original_offsets() -> None:
    for apostrophe in ("'", "’"):
        known_name = f"Siobhan D{apostrophe}Avila"
        for written in ("Siobhan D'Avila", "S. D’Avila", "D’Avila, Siobhan"):
            original = f"Résumé reviewed with {written}."
            ranges = known_name_ranges(original, known_name)
            assert len(ranges) == 1
            assert original[ranges[0].start : ranges[0].end] == written
            for patient_name, provider_name in ((known_name, ""), ("", known_name)):
                with pytest.raises(ValueError):
                    verify_text_changes(
                        original,
                        original,
                        (),
                        _miss_all_entities,
                        free_text=True,
                        patient_name=patient_name,
                        provider_name=provider_name,
                    )

        # Name boundaries do not permit a different, longer surname to become
        # corroborated evidence for the current record's person.
        assert not known_name_ranges("Reviewed Siobhan D'Avilano.", known_name)


def test_clinical_code_and_role_context_do_not_authorize_identifying_values() -> None:
    for original in (
        "SNOMED CT 73211009.",
        "SNOMED:195967001; RxNorm 860975.",
        "SNOMED CT: 38341003; LOINC 718-7.",
    ):
        verify_text_changes(original, original, (), _miss_all_entities, free_text=True)
        with pytest.raises(ValueError):
            verify_text_changes(
                original + " Phone: +44 20 7946 0857.",
                original + " Phone: +44 20 7946 0857.",
                (),
                _miss_all_entities,
                free_text=True,
            )
        with pytest.raises(ValueError):
            verify_text_changes(
                "Patient: " + original,
                "Patient: " + original,
                (),
                _miss_all_entities,
                free_text=True,
            )

    def mistake_role_for_person(text: str) -> tuple[TextEntity, ...]:
        role = text.split()[0].rstrip(":")
        return (TextEntity(start=0, end=len(role), text=role, entity_type="person"),)

    for original in ("Patient is 42 years old.", "Mother was 65 years old."):
        verify_text_changes(
            original, original, (), mistake_role_for_person, free_text=True
        )
    for original in (
        "Patient: Lena Moreau.",
        "Mother: I. Moreau.",
        "Patient Moreau.",
        "Patient is Lena Moreau.",
        "Mother was I. Moreau.",
    ):
        with pytest.raises(ValueError):
            verify_text_changes(
                original, original, (), mistake_role_for_person, free_text=True
            )


def test_unicode_forms_preserve_identifier_and_edit_coverage() -> None:
    for original in (
        "Reviewed with Jose\u0301 Silva.",
        "Reviewed with Ｊｏｓé Ｓｉｌｖａ.",
        "Call ＋４９ ３０ １２３４ ５６７８.",
        "Call +٤٩ ٣٠ ١٢٣٤ ٥٦٧٨.",
    ):
        with pytest.raises(ValueError):
            verify_text_changes(
                original,
                original,
                (),
                _miss_all_entities,
                free_text=True,
                patient_name="José Silva",
            )

    original = "ﬁle reviewed with Jose\u0301 Silva."
    name = "Jose\u0301 Silva"
    start = original.index(name)
    edit = TextEdit(
        start=start,
        end=start + len(name),
        original=name,
        replacement="Mateo Rivas",
        kind="patient_name",
    )
    verify_text_changes(
        original,
        apply_text_edits(original, (edit,)),
        (edit,),
        _miss_all_entities,
        free_text=True,
        patient_name="José Silva",
    )
    # Replacing just the base character must not claim a combining mark that
    # composes across the edit boundary in the canonical view.
    partial = TextEdit(
        start=0, end=1, original="e", replacement="a", kind="patient_name"
    )
    with pytest.raises(ValueError):
        verify_text_changes(
            "e\u0301", "a\u0301", (partial,), _miss_all_entities, free_text=True
        )
