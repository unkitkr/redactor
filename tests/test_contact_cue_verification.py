"""Saved contact labels need a complete typed edit and cannot hide extra PHI."""

from pathlib import Path

import pytest

from redactor.policy.text import apply_text_edits
from redactor.schemas.entities import TextEntity
from redactor.schemas.redaction import TextEdit
from redactor.verification.text import verify_text_changes


def _whole_contact_line(text: str) -> tuple[TextEntity, ...]:
    start = text.rfind("\n") + 1
    return (
        TextEntity(
            start=start, end=len(text), text=text[start:], entity_type="organization"
        ),
    )


def test_saved_contact_cues_require_typed_complete_contact_edits(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source.txt"
    saved = tmp_path / "saved.txt"
    cases = (
        ("Call ", "206-555-0101", "212-555-0198", "phone"),
        ("Telephone: ", "+44 20 7946 0958", "+33 1 42 68 53 00", "phone"),
        ("Fax = ", "(415) 555-0123", "(212) 555-0198", "phone"),
        ("Tel. ", "4155550123", "2125550198", "phone"),
        ("Email: ", "person.one@example.org", "person.two@example.net", "email"),
    )
    for cue, original_contact, replacement, kind in cases:
        original = f"Glucose 106 mg/dL.\n{cue}{original_contact}"
        start = original.index(original_contact)
        edits = (
            TextEdit(
                start=start,
                end=start + len(original_contact),
                original=original_contact,
                replacement=replacement,
                kind=kind,
            ),
        )
        source.write_text(original)
        saved.write_text(apply_text_edits(original, edits))
        verify_text_changes(
            source.read_text(),
            saved.read_text(),
            edits,
            _whole_contact_line,
            free_text=True,
        )
        assert "Glucose 106 mg/dL." in saved.read_text()
        for suffix in (" Avery", " ext 947", " R."):
            changed = original + suffix
            source.write_text(changed)
            saved.write_text(apply_text_edits(changed, edits))
            with pytest.raises(ValueError, match="residual_phi_detected"):
                verify_text_changes(
                    source.read_text(),
                    saved.read_text(),
                    edits,
                    _whole_contact_line,
                    free_text=True,
                )
        for wrong in ("person_name", "identifier"):
            with pytest.raises(ValueError, match="residual_phi_detected"):
                verify_text_changes(
                    original,
                    apply_text_edits(original, edits),
                    (edits[0].model_copy(update={"kind": wrong}),),
                    _whole_contact_line,
                    free_text=True,
                )
        with pytest.raises(ValueError, match="clinical_content_changed"):
            verify_text_changes(
                original,
                apply_text_edits(original, edits).replace(cue, "Contact: "),
                edits,
                _whole_contact_line,
                free_text=True,
            )

    original = "Dr. Call 206-555-0101"
    start = original.index("206")
    edits = (
        TextEdit(
            start=start,
            end=len(original),
            original=original[start:],
            replacement="212-555-0198",
            kind="phone",
        ),
    )
    with pytest.raises(ValueError, match="residual_phi_detected"):
        verify_text_changes(
            original,
            apply_text_edits(original, edits),
            edits,
            _whole_contact_line,
            free_text=True,
        )


def test_saved_temporal_join_requires_both_typed_edits_and_no_extra_words(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source.txt"
    saved = tmp_path / "saved.txt"
    for label, contact, replacement, kind, relation in (
        ("Fax ", "415.555.0182", "212.555.0194", "phone", "after"),
        (
            "Email: ",
            "person.one@example.org",
            "person.two@example.net",
            "email",
            "by",
        ),
    ):
        for gap, accepted in (
            (f" {relation} ", True),
            (f" Avery {relation} ", False),
            (f" ext 947 {relation} ", False),
            (f"\n{relation} ", False),
        ):
            original = f"Glucose 106 mg/dL.\n{label}{contact}{gap}2027-03-14"
            start = original.index(contact)
            date_start = original.index("2027-03-14")
            edits = (
                TextEdit(
                    start=start,
                    end=start + len(contact),
                    original=contact,
                    replacement=replacement,
                    kind=kind,
                ),
                TextEdit(
                    start=date_start,
                    end=date_start + 10,
                    original="2027-03-14",
                    replacement="2027-06-02",
                    kind="date",
                ),
            )
            source.write_text(original)
            saved.write_text(apply_text_edits(original, edits))
            if not accepted:
                with pytest.raises(ValueError, match="residual_phi_detected"):
                    verify_text_changes(
                        source.read_text(),
                        saved.read_text(),
                        edits,
                        _whole_contact_line,
                        free_text=True,
                    )
                continue
            verify_text_changes(
                source.read_text(),
                saved.read_text(),
                edits,
                _whole_contact_line,
                free_text=True,
            )
            for incomplete in (
                edits[:1],
                (edits[0], edits[1].model_copy(update={"kind": "identifier"})),
            ):
                with pytest.raises(ValueError, match="residual_phi_detected"):
                    verify_text_changes(
                        original,
                        apply_text_edits(original, incomplete),
                        incomplete,
                        _whole_contact_line,
                        free_text=True,
                    )
            with pytest.raises(ValueError, match="clinical_content_changed"):
                verify_text_changes(
                    original,
                    saved.read_text().replace(f" {relation} ", " since "),
                    edits,
                    _whole_contact_line,
                    free_text=True,
                )
