"""Preserve labelled clinical codes only after validating their supported syntax.

SCTID constraints and check-digit definition:
https://docs.snomed.org/snomed-ct-specifications/snomed-ct-release-file-specification/snomed-ct-identifiers/6.3-sctid-constraints
"""

import re

from redactor.schemas.redaction import TextRange
from redactor.utils.constants import (
    SNOMED_CONCEPT_ID_PATTERN,
    SNOMED_CONCEPT_PARTITIONS,
    SNOMED_EXTENSION_MINIMUM_DIGITS,
    SNOMED_EXTENSION_PARTITION,
    SNOMED_LABELLED_CODE_PATTERN,
    VERHOEFF_MULTIPLICATION,
    VERHOEFF_PERMUTATIONS,
)


def snomed_ranges(text: str) -> tuple[TextRange, ...]:
    """Only the literal label and its validated code form a clinical expression."""
    return tuple(
        TextRange(start=match.start(), end=match.end())
        for match in re.finditer(SNOMED_LABELLED_CODE_PATTERN, text)
        if is_snomed_concept_id(match["code"])
    )


def is_snomed_concept_id(identifier: str) -> bool:
    """Check concept syntax; no assertion is made about release membership."""
    if re.fullmatch(SNOMED_CONCEPT_ID_PATTERN, identifier) is None:
        return False
    # The two digits immediately before the checksum identify the component.
    partition = identifier[-3:-1]
    if partition not in SNOMED_CONCEPT_PARTITIONS:
        return False
    if partition == SNOMED_EXTENSION_PARTITION and (
        len(identifier) < SNOMED_EXTENSION_MINIMUM_DIGITS
    ):
        return False
    checksum = 0
    for position, digit in enumerate(reversed(identifier)):
        permutation = VERHOEFF_PERMUTATIONS[position % len(VERHOEFF_PERMUTATIONS)]
        checksum = VERHOEFF_MULTIPLICATION[checksum][permutation[int(digit)]]
    return checksum == 0
