"""Validate code syntax independently of particular diagnoses or model findings."""

import pytest

from redactor.inference.text import find_text_phi
from redactor.policy.clinical_codes import is_snomed_concept_id, snomed_ranges
from redactor.schemas.entities import TextEntity
from redactor.verification.text import verify_text_changes


def _miss_all_entities(_text: str) -> tuple[TextEntity, ...]:
    return ()


def test_snomed_boundaries_partitions_and_checksums() -> None:
    # Independent vectors from the specification's example identifiers, including
    # short-format and extension concepts and both supported length boundaries.
    for identifier in (
        "100005",
        "1290023401004",
        "11000001102",
        "10989121108",
        "1290989121103",
        "999999990989121104",
    ):
        assert is_snomed_concept_id(identifier)
        for label in ("SNOMED", "SNOMED CT:", "snomed#"):
            original = f"Diagnosis {label} {identifier}."
            ranges = snomed_ranges(original)
            assert len(ranges) == 1
            assert original[ranges[0].start : ranges[0].end] == f"{label} {identifier}"
            assert not find_text_phi(original, _miss_all_entities)
            verify_text_changes(
                original, original, (), _miss_all_entities, free_text=True
            )
        assert not is_snomed_concept_id(
            identifier[:-1] + str((int(identifier[-1]) + 1) % 10)
        )

    for identifier in (
        "10005",  # Too short.
        "100000",  # Invalid minimum value/checksum.
        "9999999990989121104",  # Too long.
        "0100005",  # Leading zero.
        "100014",  # Description, not a concept.
        "100022",  # Relationship, not a concept.
        "1290000001117",  # Extension description.
        "110102",  # No room for extension namespace.
        "１００００５",  # Non-ASCII decimal digits.
        "10000٥",  # Mixed decimal alphabets.
        "+100005",
        "100005.0",
        "100005A",
    ):
        assert not is_snomed_concept_id(identifier)
        assert not snomed_ranges(f"SNOMED CT: {identifier}")


def test_labelled_codes_never_override_contact_or_identifier_evidence() -> None:
    for original in (
        "Phone: SNOMED CT 73211009.",
        "Patient: SNOMED CT 73211009.",
        "SNOMED CT 73211009 ext:42.",
        "SNOMED CT: 73211008.",  # Incorrect check digit.
        "SNOMED CT: +73211009.",
        "SNOMED CT: 0073211009.",
        "SNOMED CT: ７３２１１００９.",
        "SNOMED CT: 9999999990989121104.",
    ):
        with pytest.raises(ValueError):
            verify_text_changes(
                original, original, (), _miss_all_entities, free_text=True
            )
