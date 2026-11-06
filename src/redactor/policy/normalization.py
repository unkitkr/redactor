"""Conservative spelling normalization; matching names alone never merges people."""

import re
import unicodedata

from redactor.utils.constants import NAME_TITLES, UNICODE_NORMAL_FORM
from redactor.utils.errors import ERROR_IDENTIFIER


def normalize_name(value: str) -> str:
    normalized = unicodedata.normalize(UNICODE_NORMAL_FORM, value).strip().casefold()
    if "^" in normalized:
        # DICOM and HL7 family^given^middle^prefix^suffix name components.
        components = normalized.split("^")
        if len(components) > 5:
            raise ValueError(ERROR_IDENTIFIER)
        normalized = " ".join((*components[1:3], components[0], *components[4:5]))
    elif "," in normalized:
        family, given = normalized.split(",", maxsplit=1)
        normalized = f"{given} {family}"
    words = normalized.split()
    while words and words[0].rstrip(".") in NAME_TITLES:
        words.pop(0)
    # An initial stays an initial. Diacritics, hyphens and apostrophes remain.
    return " ".join(word.rstrip(".") for word in words)


def normalize_identifier(value: str) -> str:
    """Keep leading zeroes and case: they can distinguish opaque identifiers."""
    normalized = unicodedata.normalize(UNICODE_NORMAL_FORM, value).strip()
    if not normalized:
        raise ValueError(ERROR_IDENTIFIER)
    return normalized


def normalize_digits(value: str) -> str:
    """Remove conventional separators without silently dropping arbitrary text."""
    normalized = unicodedata.normalize(UNICODE_NORMAL_FORM, value).strip()
    if not re.fullmatch(r"\+?[0-9 ().-]+", normalized):
        raise ValueError(ERROR_IDENTIFIER)
    digits = "".join(character for character in normalized if character.isdigit())
    if not digits:
        raise ValueError(ERROR_IDENTIFIER)
    return digits
