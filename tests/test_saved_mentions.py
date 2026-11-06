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

    for suffix in (";", ",", " Moreno;"):
        original = "Alina Stone" + suffix
        finding = TextFinding(
            start=0, end=len("Alina Stone"), original="Alina Stone", kind="person_name"
        )
        edits = text_edits((finding,), context, bytes(range(32)))
        source = tmp_path / "punctuation-source.txt"
        saved = tmp_path / "punctuation-saved.txt"
        source.write_text(original)
        saved.write_text(apply_text_edits(original, edits))
        if suffix == " Moreno;":
            with pytest.raises(ValueError, match="residual_phi_detected"):
                verify_text_changes(
                    source.read_text(),
                    saved.read_text(),
                    edits,
                    _whole_prediction,
                    free_text=True,
                )
        else:
            verify_text_changes(
                source.read_text(),
                saved.read_text(),
                edits,
                _whole_prediction,
                free_text=True,
            )

    for prefix in ("-- ", "— ", "( ", " Leena ", "-- R. "):
        original = prefix + "Alina Stone"
        finding = TextFinding(
            start=len(prefix),
            end=len(original),
            original="Alina Stone",
            kind="person_name",
        )
        edits = text_edits((finding,), context, bytes(range(32)))
        source = tmp_path / "prefix-source.txt"
        saved = tmp_path / "prefix-saved.txt"
        source.write_text(original)
        saved.write_text(apply_text_edits(original, edits))
        if prefix in (" Leena ", "-- R. "):
            with pytest.raises(ValueError, match="residual_phi_detected"):
                verify_text_changes(
                    source.read_text(),
                    saved.read_text(),
                    edits,
                    _whole_prediction,
                    free_text=True,
                )
        else:
            verify_text_changes(
                source.read_text(),
                saved.read_text(),
                edits,
                _whole_prediction,
                free_text=True,
            )


def _whole_prediction(text: str) -> tuple[TextEntity, ...]:
    return (TextEntity(start=0, end=len(text), text=text, entity_type="person"),)


def test_saved_role_predicate_does_not_exempt_an_unedited_name(tmp_path: Path) -> None:
    source = tmp_path / "source.txt"
    saved = tmp_path / "saved.txt"
    source.write_text("spouse Alina Stone assists. Creatinine 1.20 mg/dL.")
    context = TextContext(context_key="record", maximum_date_shift_days=365)
    for name in ("Alina Stone", "Alina"):
        finding = TextFinding(
            start=7, end=7 + len(name), original=name, kind="person_name"
        )
        edits = text_edits((finding,), context, bytes(range(32)))
        saved.write_text(apply_text_edits(source.read_text(), edits))
        if name == "Alina":
            with pytest.raises(ValueError, match="residual_phi_detected"):
                verify_text_changes(
                    source.read_text(),
                    saved.read_text(),
                    edits,
                    _predicate_prediction,
                    free_text=True,
                )
        else:
            verify_text_changes(
                source.read_text(),
                saved.read_text(),
                edits,
                _predicate_prediction,
                free_text=True,
            )


def _predicate_prediction(text: str) -> tuple[TextEntity, ...]:
    start = text.index("assists")
    return (
        TextEntity(
            start=start,
            end=start + 7,
            text="assists",
            entity_type="location",
            label="location city",
        ),
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
