"""Check saved text with broad predictions and deliberately omitted names."""

import re
from pathlib import Path

import pytest

from redactor.policy.text import apply_text_edits, text_edits
from redactor.schemas.entities import TextEntity
from redactor.schemas.redaction import TextContext, TextFinding
from redactor.verification.text import verify_text_changes


def test_saved_mentions_require_every_name_fragment_to_be_replaced(
    tmp_path: Path,
) -> None:
    context = TextContext(context_key="document-context", maximum_date_shift_days=365)
    for index, joining in enumerate((" & ", " ", " and ", " Leena ")):
        original = f"Dr. Alina Stone{joining}Mateo Kaur. Creatinine 1.20 mg/dL."
        findings = tuple(
            TextFinding(
                start=original.index(name),
                end=original.index(name) + len(name),
                original=name,
                kind="person_name",
            )
            for name in ("Alina Stone", "Mateo Kaur")
        )
        edits = text_edits(findings, context, bytes(range(32)))
        source = tmp_path / f"source-{index}.txt"
        saved = tmp_path / f"saved-{index}.txt"
        source.write_text(original)
        saved.write_text(apply_text_edits(original, edits))
        if joining in (" Leena ", " "):
            # A broad prediction cannot authorize an unedited middle name merely
            # because there are two verified surrogate names around it.
            # The space-only case is also one explicitly labelled four-part
            # provider name, so deterministic evidence requires one complete edit.
            with pytest.raises(ValueError, match="residual_phi_detected"):
                verify_text_changes(
                    source.read_text(),
                    saved.read_text(),
                    edits,
                    _broad_prediction,
                    free_text=True,
                )
        else:
            verify_text_changes(
                source.read_text(),
                saved.read_text(),
                edits,
                _broad_prediction,
                free_text=True,
            )
            verify_text_changes(
                source.read_text(),
                saved.read_text(),
                edits,
                _partial_prediction,
                free_text=True,
            )
        saved.write_text(saved.read_text().replace("1.20", "1.21"))
        with pytest.raises(ValueError):
            verify_text_changes(
                source.read_text(),
                saved.read_text(),
                edits,
                _broad_prediction,
                free_text=True,
            )

    for role in ("Daughter", "Brother", "Dr."):
        original = f"{role} Alina Stone assisted. Creatinine 1.20 mg/dL."
        start = original.index("Alina")
        findings = (
            TextFinding(
                start=start,
                end=start + len("Alina Stone"),
                original="Alina Stone",
                kind="person_name",
            ),
        )
        edits = text_edits(findings, context, bytes(range(32)))
        source = tmp_path / "role-source.txt"
        saved = tmp_path / "role-saved.txt"
        source.write_text(original)
        saved.write_text(apply_text_edits(original, edits))
        verify_text_changes(
            source.read_text(),
            saved.read_text(),
            edits,
            _role_prediction,
            free_text=True,
        )


def _role_prediction(text: str) -> tuple[TextEntity, ...]:
    end = text.index(" ")
    return (TextEntity(start=0, end=end, text=text[:end], entity_type="person"),)


def _broad_prediction(text: str) -> tuple[TextEntity, ...]:
    end = text.index(". Creatinine")
    return (
        TextEntity(
            start=0, end=end, text=text[:end], entity_type="person", label="name"
        ),
    )


def _partial_prediction(text: str) -> tuple[TextEntity, ...]:
    match = re.match(r"Dr\. [A-Za-z]+", text)
    assert match is not None
    return (
        TextEntity(
            start=0, end=match.end(), text=match[0], entity_type="person", label="name"
        ),
    )
