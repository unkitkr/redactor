"""Grounding and deterministic detection for the verified failure families.

Each test mirrors one diagnosed record family: unlabeled identifiers beside a
bound name, facility blocks and labelled organization values, specialty
organizations that reach into protected labels, url-labeled clinical
fragments, abbreviation-shaped organizations and name-shaped OCR lines.
"""

from pathlib import Path

import pytest

from redactor.inference.deterministic_text import prepare_text_phi
from redactor.inference.model_loader import load_local_ner
from redactor.inference.semantics import possible_entity
from redactor.inference.text import find_text_phi, finish_text_phi
from redactor.policy.identifiers import replace_identifier
from redactor.policy.text import apply_text_edits, text_edits
from redactor.schemas.configuration import LocalSettings
from redactor.schemas.entities import PreparedTextAssessment, TextEntity
from redactor.schemas.redaction import TextContext, TextRange
from redactor.utils.constants import MRN_NAMESPACE
from redactor.utils.errors import ERROR_COVERAGE
from redactor.verification.text import verify_text_changes

KEY = bytes(range(32))


def _context() -> TextContext:
    return TextContext(context_key="grounding-record", maximum_date_shift_days=365)


def _organization(text: str, value: str) -> TextEntity:
    start = text.index(value)
    return TextEntity(
        start=start, end=start + len(value), text=value, entity_type="organization"
    )


def _contact(text: str, value: str, label: str) -> TextEntity:
    start = text.index(value)
    return TextEntity(
        start=start,
        end=start + len(value),
        text=value,
        entity_type="contact",
        label=label,
    )


def test_identifier_digits_beside_a_bound_name_are_pseudonymized(
    tmp_path: Path,
) -> None:
    """An unlabeled patient identifier travelling with the name is still PHI."""
    ner = load_local_ner(LocalSettings())
    value = "Kowalczyk, Bernard 0090574"
    prepared = prepare_text_phi(value, patient_name="Bernard Kowalczyk")
    kinds = {(finding.kind, finding.namespace) for finding in prepared.findings}
    assert kinds == {("patient_name", ""), ("identifier", MRN_NAMESPACE)}
    findings = finish_text_phi(prepared, lambda _text: ())
    edits = text_edits(findings, _context(), KEY)
    saved = tmp_path / "identifier.txt"
    saved.write_text(apply_text_edits(value, edits))
    verify_text_changes(value, saved.read_text(), edits, ner, free_text=True)
    assert "0090574" not in saved.read_text() and "Kowalczyk" not in saved.read_text()
    assert edits[1].replacement == replace_identifier(
        "0090574", KEY, namespace=MRN_NAMESPACE
    )


def test_identifier_digits_keep_date_and_unbound_guards() -> None:
    """Compact dates, protected expressions and unbound names stay clinical."""
    for value, patient in (
        ("Kowalczyk, Bernard 19651016", "Bernard Kowalczyk"),
        ("Creatinine 415000 noted", ""),
    ):
        prepared = prepare_text_phi(value, patient_name=patient)
        assert not any(finding.kind == "identifier" for finding in prepared.findings), (
            value
        )
    # Accepted residual risk: a 6+ digit quantity sharing a value with the
    # bound name is pseudonymized as that person's identifier.
    prepared = prepare_text_phi(
        "B. Kowalczyk WBC 415000", patient_name="Bernard Kowalczyk"
    )
    assert any(finding.kind == "identifier" for finding in prepared.findings)


def test_facility_blocks_and_labelled_organization_values_are_deterministic(
    tmp_path: Path,
) -> None:
    """The edit spans the block a tagger would claim, including the department."""
    ner = load_local_ner(LocalSettings())
    header = "RIVERBEND GENERAL HOSPITAL - INTERNAL MEDICINE PROGRESS NOTE"
    for value, span in (
        (header, header),
        (
            "Riverbend General Hospital - Neurology consult",
            "Riverbend General Hospital - Neurology",
        ),
        ("transferred to General Hospital yesterday", "General Hospital"),
        ("HOSPITAL: MERCYLINE", "MERCYLINE"),
        (
            "Insurance: Blue Cross Blue Shield    Member ID: BCB272224964",
            "Blue Cross Blue Shield",
        ),
    ):
        prepared = prepare_text_phi(value)
        organizations = [
            finding for finding in prepared.findings if finding.kind == "organization"
        ]
        assert [finding.original for finding in organizations] == [span], value
    value = "Insurance: Blue Cross Blue Shield    Member ID: BCB272224964"
    prepared = prepare_text_phi(value)
    assert [
        (finding.kind, finding.original)
        for finding in prepared.findings
        if finding.kind == "identifier"
    ] == [("identifier", "BCB272224964")]
    findings = finish_text_phi(prepared, lambda _text: ())
    edits = text_edits(findings, _context(), KEY)
    saved = tmp_path / "facility.txt"
    saved.write_text(apply_text_edits(value, edits))
    verify_text_changes(value, saved.read_text(), edits, ner, free_text=True)
    assert "Blue Cross" not in saved.read_text()
    assert "BCB272224964" not in saved.read_text()
    for unlabelled in ("Hospital: mercyline west", "the clinic was quiet"):
        assert not any(
            finding.kind == "organization"
            for finding in prepare_text_phi(unlabelled).findings
        )


def test_specialty_organizations_ground_without_protected_labels(
    tmp_path: Path,
) -> None:
    """A specialty observation may not absorb the protected NPI label."""
    ner = load_local_ner(LocalSettings())
    value = "From: Dr. Mira Vale, Primary Care (NPI "

    def observes_specialty(text: str) -> tuple[TextEntity, ...]:
        return (_organization(text, "Primary Care (NPI"),)

    findings = find_text_phi(value, observes_specialty)
    assert [finding.original for finding in findings] == ["Mira Vale", "Primary Care"]
    assert [finding.kind for finding in findings] == ["provider_name", "organization"]
    edits = text_edits(findings, _context(), KEY)
    saved = tmp_path / "specialty.txt"
    saved.write_text(apply_text_edits(value, edits))
    verify_text_changes(value, saved.read_text(), edits, ner, free_text=True)
    assert "(NPI" in saved.read_text() and "Primary Care" not in saved.read_text()


def test_url_labeled_clinical_fragments_are_rejected_and_contacts_need_syntax() -> None:
    """Contact labels ground only on complete supported syntax."""
    clinical = (
        "type 2 diabetes (E11.9); Requested study: CT chest w/o contrast (CPT 71250)."
    )

    def observes_urls(text: str) -> tuple[TextEntity, ...]:
        return (
            _contact(text, "CT chest w/o contrast", "url"),
            _contact(text, "CPT 71250", "url"),
        )

    assert find_text_phi(clinical, observes_urls) == ()
    web = "follow up through https://portal.example/scan"
    prepared_web = PreparedTextAssessment(
        text=web,
        findings=(),
        protected=(),
        unresolved=(TextRange(start=0, end=len(web)),),
    )

    def observes_web(text: str) -> tuple[TextEntity, ...]:
        return (_contact(text, "https://portal.example/scan", "url"),)

    findings = finish_text_phi(prepared_web, observes_web)
    assert [finding.kind for finding in findings] == ["web"]
    assert findings[0].original == "https://portal.example/scan"
    malformed = "pager 4l5-555-0l52"
    prepared = PreparedTextAssessment(
        text=malformed,
        findings=(),
        protected=(),
        unresolved=(TextRange(start=0, end=len(malformed)),),
    )

    def observes_malformed_phone(text: str) -> tuple[TextEntity, ...]:
        return (_contact(text, "4l5-555-0l52", "phone number"),)

    with pytest.raises(ValueError, match=ERROR_COVERAGE):
        finish_text_phi(prepared, observes_malformed_phone)


def test_abbreviation_shaped_organizations_are_not_entities() -> None:
    """A short unpointed all-caps token is clinical vocabulary, not a facility."""
    for abbreviation in ("AAA", "TIA", "ICU", "EKG", "MUSC"):
        entity = TextEntity(
            start=0,
            end=len(abbreviation),
            text=abbreviation,
            entity_type="organization",
        )
        assert not possible_entity(entity), abbreviation
    for organization in ("INC", "Hospitals", "Riverbend General Hospital"):
        entity = TextEntity(
            start=0,
            end=len(organization),
            text=organization,
            entity_type="organization",
        )
        assert possible_entity(entity), organization
    comment = "Wife Selma Vale; history of TIA."

    def observes_abbreviation(text: str) -> tuple[TextEntity, ...]:
        return (_organization(text, "TIA"),)

    findings = find_text_phi(comment, observes_abbreviation)
    assert [finding.kind for finding in findings] == ["relative"]


def test_name_shaped_organization_labels_ground_as_person_names(
    tmp_path: Path,
) -> None:
    """A mislabeled organization on a lone name line pseudonymizes the person."""
    ner = load_local_ner(LocalSettings())
    value = "KOWALCZYK, BERNARD"

    def observes_given_name(text: str) -> tuple[TextEntity, ...]:
        return (_organization(text, "BERNARD"),)

    findings = find_text_phi(value, observes_given_name)
    assert [finding.kind for finding in findings] == ["person_name"]
    assert findings[0].original == value
    edits = text_edits(findings, _context(), KEY)
    saved = tmp_path / "wristband.txt"
    saved.write_text(apply_text_edits(value, edits))
    verify_text_changes(value, saved.read_text(), edits, ner, free_text=True)
    assert "KOWALCZYK" not in saved.read_text() and "BERNARD" not in saved.read_text()

    def observes_both_tokens(text: str) -> tuple[TextEntity, ...]:
        return (_organization(text, "KOWALCZYK"), _organization(text, "BERNARD"))

    assert find_text_phi(value, observes_both_tokens) == findings


def test_facility_shaped_lines_never_ground_as_person_names() -> None:
    """Organization vocabulary on the line keeps the fail-closed facility path."""
    facility = "Lakeview Imaging Center"

    def observes_partial(text: str) -> tuple[TextEntity, ...]:
        return (_organization(text, "Lakeview"),)

    findings = find_text_phi(facility, observes_partial)
    assert [finding.kind for finding in findings] == ["organization"]
    assert findings[0].original == facility

    def observes_word(text: str) -> tuple[TextEntity, ...]:
        return (_organization(text, "Imaging"),)

    assert find_text_phi(facility, observes_word) == findings
    partial = "seen at the Center today"

    def observes_suffix(text: str) -> tuple[TextEntity, ...]:
        return (_organization(text, "Center"),)

    with pytest.raises(ValueError, match=ERROR_COVERAGE):
        find_text_phi(partial, observes_suffix)
