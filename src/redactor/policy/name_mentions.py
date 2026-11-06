"""Locate full and initial spellings inside an already established record context."""

import re

from redactor.policy.normalization import normalize_name
from redactor.schemas.redaction import TextRange
from redactor.utils.constants import (
    VERIFIER_NAME_APOSTROPHE_PATTERN,
    VERIFIER_NAME_BOUNDARY_END,
    VERIFIER_NAME_BOUNDARY_START,
)


def known_name_ranges(text: str, name: str) -> tuple[TextRange, ...]:
    """Match corroborated names and initial forms only inside the current record."""
    words = normalize_name(name).split()
    if not words:
        return ()
    family = _name_word_pattern(words[-1])
    pattern = family
    if len(words) > 1:
        given = _given_name_pattern(words[0])
        middle = "".join(
            rf"(?:[ \t]+{_given_name_pattern(word)})?" for word in words[1:-1]
        )
        pattern = rf"(?:{given}{middle}[ \t]+{family}|{family},[ \t]*{given}{middle})"
    return tuple(
        TextRange(start=match.start(), end=match.end())
        for match in re.finditer(
            VERIFIER_NAME_BOUNDARY_START + pattern + VERIFIER_NAME_BOUNDARY_END,
            text,
            re.IGNORECASE,
        )
    )


def _given_name_pattern(word: str) -> str:
    if len(word) == 1:
        return re.escape(word) + r"[^\W\d_]*\.?"
    return rf"(?:{_name_word_pattern(word)}|{re.escape(word[0])}\.?)"


def _name_word_pattern(word: str) -> str:
    """Permit typographic apostrophes without rewriting text or its offsets."""
    return VERIFIER_NAME_APOSTROPHE_PATTERN.join(
        re.escape(part) for part in re.split(VERIFIER_NAME_APOSTROPHE_PATTERN, word)
    )
