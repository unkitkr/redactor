"""Saved text joins proven spans without authorizing unedited name fragments."""

from pathlib import Path

import pytest

from redactor.policy.text import apply_text_edits
from redactor.schemas.entities import TextEntity
from redactor.schemas.redaction import TextEdit
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
