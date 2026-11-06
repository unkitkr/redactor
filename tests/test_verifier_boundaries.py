"""Saved text joins proven spans without authorizing unedited name fragments."""

from pathlib import Path

import pytest

from redactor.policy.text import apply_text_edits
from redactor.schemas.entities import TextEntity
from redactor.schemas.redaction import TextEdit
from redactor.utils.constants import IMAGE_DESCRIPTION_FIELD_LABEL
from redactor.verification.text import verify_text_changes


def _whole_surface_person(text: str) -> tuple[TextEntity, ...]:
    """A controlled independent NER boundary overextends an entity prediction."""
    return (TextEntity(start=0, end=len(text), text=text, entity_type="person"),)


@pytest.mark.parametrize(
    ("heading", "name", "clinical"),
    (
        ("Progress note", "Amina Keller", "Metformin 850 mg BID."),
        ("Referral letter", "Nadia Velez", "BP 118/74 mmHg."),
        ("Clinical note", "Ivo Marin", "Glucose 106 mg/dL."),
    ),
)
def test_saved_cross_boundary_predictions_require_complete_proof(
    tmp_path: Path, heading: str, name: str, clinical: str
) -> None:
    source = tmp_path / "source.txt"
    saved = tmp_path / "saved.txt"
    original = f"{heading}\n{name}; {clinical}"
    source.write_text(original)
    start = original.index(name)
    edits = (
        TextEdit(
            start=start,
            end=start + len(name),
            original=name,
            replacement="Robin Avery",
            kind="person_name",
        ),
    )
    saved.write_text(apply_text_edits(original, edits))
    verify_text_changes(
        source.read_text(),
        saved.read_text(),
        edits,
        _whole_surface_person,
        free_text=True,
    )
    assert clinical in saved.read_text()
    assert source.read_text() == original
    for leaked in (" R.", " 7", " Unknown", "\u0301", " +"):
        changed = original.replace(f"{name};", f"{name}{leaked};")
        source.write_text(changed)
        saved.write_text(apply_text_edits(changed, edits))
        with pytest.raises(ValueError, match="residual_phi_detected"):
            verify_text_changes(
                source.read_text(),
                saved.read_text(),
                edits,
                _whole_surface_person,
                free_text=True,
            )
    source.write_text(original)
    # A serialized clinical change is rejected before model-boundary handling.
    saved.write_text(apply_text_edits(original, edits).replace(clinical, "Changed."))
    with pytest.raises(ValueError, match="clinical_content_changed"):
        verify_text_changes(
            source.read_text(),
            saved.read_text(),
            edits,
            _whole_surface_person,
            free_text=True,
        )


@pytest.mark.parametrize(
    ("heading", "separator", "name"),
    (
        ("Discharge summary", " - ", "Leila Mercier"),
        ("Referral letter", ": ", "Omar Stein"),
        ("Clinical note", " — ", "Nadia Velez"),
    ),
)
def test_saved_title_prefix_requires_an_adjacent_verified_edit(
    tmp_path: Path, heading: str, separator: str, name: str
) -> None:
    original = f"{heading}{separator}{name}"
    start = len(heading + separator)
    edit = TextEdit(
        start=start,
        end=len(original),
        original=name,
        replacement="Robin Avery",
        kind="person_name",
    )
    saved = tmp_path / "saved-title.txt"
    saved.write_text(apply_text_edits(original, (edit,)))
    verify_text_changes(
        original, saved.read_text(), (edit,), _whole_surface_person, free_text=True
    )
    with pytest.raises(ValueError, match="residual_phi_detected"):
        verify_text_changes(
            original, original, (), _whole_surface_person, free_text=True
        )
    for suffix in (" J.", " Other", " 5"):
        leaked = original + suffix
        saved.write_text(apply_text_edits(leaked, (edit,)))
        with pytest.raises(ValueError, match="residual_phi_detected"):
            verify_text_changes(
                leaked,
                saved.read_text(),
                (edit,),
                _whole_surface_person,
                free_text=True,
            )
    saved.write_text(apply_text_edits(original, (edit,)).replace(heading, "Changed"))
    with pytest.raises(ValueError, match="clinical_content_changed"):
        verify_text_changes(
            original, saved.read_text(), (edit,), _whole_surface_person, free_text=True
        )


def test_output_context_adapter_remains_separate_during_normalization(
    tmp_path: Path,
) -> None:
    original, output = "Zoe\u0308 Marin", "Rene\u0301 Calder"
    edit = TextEdit(
        start=0,
        end=len(original),
        original=original,
        replacement=output,
        kind="person_name",
    )
    source_seen: list[str] = []
    output_seen: list[str] = []

    def source_ner(text: str) -> tuple[TextEntity, ...]:
        assert text in (original, "Zoë Marin")
        source_seen.append(text)
        return _whole_surface_person(text)

    def saved_ner(text: str) -> tuple[TextEntity, ...]:
        assert text in (output, "René Calder")
        output_seen.append(text)
        return _whole_surface_person(text)

    saved = tmp_path / "normalized-context.txt"
    saved.write_text(output)
    verify_text_changes(
        original,
        saved.read_text(),
        (edit,),
        source_ner,
        free_text=True,
        output_ner=saved_ner,
    )
    assert source_seen == [original, "Zoë Marin"]
    assert output_seen == [output, "René Calder"]


@pytest.mark.parametrize("descriptor", ("Photo ID of ", "Portrait of ", "Image of "))
def test_image_description_proof_requires_exact_slot_and_complete_person_edit(
    tmp_path: Path,
    descriptor: str,
) -> None:
    name = "Alina Calder"
    source = descriptor + name + "."
    edit = TextEdit(
        start=len(descriptor),
        end=len(descriptor + name),
        original=name,
        replacement="Robin Avery",
        kind="person_name",
    )
    saved = tmp_path / "description.txt"
    saved.write_text(apply_text_edits(source, (edit,)))
    verify_text_changes(
        source,
        saved.read_text(),
        (edit,),
        _whole_surface_person,
        free_text=True,
        field_label=IMAGE_DESCRIPTION_FIELD_LABEL,
    )
    for label in ("", "Caption", "Custom description"):
        with pytest.raises(ValueError, match="residual_phi_detected"):
            verify_text_changes(
                source,
                saved.read_text(),
                (edit,),
                _whole_surface_person,
                free_text=True,
                field_label=label,
            )
    for before, after in (("Leena ", ""), ("", " Moreno"), ("", " 4")):
        altered = descriptor + before + name + after + "."
        shifted = edit.model_copy(
            update={"start": edit.start + len(before), "end": edit.end + len(before)}
        )
        saved.write_text(apply_text_edits(altered, (shifted,)))
        with pytest.raises(ValueError, match="residual_phi_detected"):
            verify_text_changes(
                altered,
                saved.read_text(),
                (shifted,),
                _whole_surface_person,
                free_text=True,
                field_label=IMAGE_DESCRIPTION_FIELD_LABEL,
            )


@pytest.mark.parametrize("cue", ("Printed ", "Generated: ", "Exported = "))
def test_provenance_date_cue_requires_a_verified_date(tmp_path: Path, cue: str) -> None:
    original = cue + "2024-04-09"
    edit = TextEdit(
        start=len(cue),
        end=len(original),
        original="2024-04-09",
        replacement="2023-05-12",
        kind="date",
    )
    saved = tmp_path / "footer.txt"
    saved.write_text(apply_text_edits(original, (edit,)))
    verify_text_changes(
        original, saved.read_text(), (edit,), _whole_surface_person, free_text=True
    )
    for extra in (" Amina", " 7", " J."):
        leaked = original + extra
        saved.write_text(apply_text_edits(leaked, (edit,)))
        with pytest.raises(ValueError, match="residual_phi_detected"):
            verify_text_changes(
                leaked,
                saved.read_text(),
                (edit,),
                _whole_surface_person,
                free_text=True,
            )
