"""Locate full and initial spellings inside an already established record context."""

import re
from collections.abc import Callable
from functools import lru_cache

from redactor.policy.normalization import normalize_name
from redactor.schemas.redaction import TextRange
from redactor.utils.constants import (
    VERIFIER_NAME_APOSTROPHE_PATTERN,
    VERIFIER_NAME_BOUNDARY_END,
    VERIFIER_NAME_BOUNDARY_START,
)

_NAME_APOSTROPHE = re.compile(VERIFIER_NAME_APOSTROPHE_PATTERN)


def known_name_ranges(text: str, name: str) -> tuple[TextRange, ...]:
    """Match corroborated names and initial forms only inside the current record."""
    return _matched_ranges(text, _name_pattern(name))


def make_name_matcher(
    *, maximum_entries: int, maximum_name_characters: int
) -> Callable[[str, str], tuple[TextRange, ...]]:
    """Keep compiled name patterns local and bounded, without caching role evidence."""
    cached = lru_cache(maxsize=maximum_entries)(_name_pattern)

    def locate(text: str, name: str) -> tuple[TextRange, ...]:
        pattern = (
            cached(name)
            if len(name) <= maximum_name_characters
            else _name_pattern(name)
        )
        return _matched_ranges(text, pattern)

    return locate


def _name_pattern(name: str) -> re.Pattern[str] | None:
    words = normalize_name(name).split()
    if not words:
        return None
    family = _name_word_pattern(words[-1])
    pattern = family
    if len(words) > 1:
        given = _given_name_pattern(words[0])
        middle = "".join(
            rf"(?:[ \t]+{_given_name_pattern(word)})?" for word in words[1:-1]
        )
        pattern = rf"(?:{given}{middle}[ \t]+{family}|{family},[ \t]*{given}{middle})"
    return re.compile(
        VERIFIER_NAME_BOUNDARY_START + pattern + VERIFIER_NAME_BOUNDARY_END,
        re.IGNORECASE,
    )


def _matched_ranges(
    text: str, pattern: re.Pattern[str] | None
) -> tuple[TextRange, ...]:
    return (
        tuple(
            TextRange(start=match.start(), end=match.end())
            for match in pattern.finditer(text)
        )
        if pattern is not None
        else ()
    )


def _given_name_pattern(word: str) -> str:
    if len(word) == 1:
        return re.escape(word) + r"[^\W\d_]*\.?"
    return rf"(?:{_name_word_pattern(word)}|{re.escape(word[0])}\.?)"


def _name_word_pattern(word: str) -> str:
    """Permit typographic apostrophes without rewriting text or its offsets."""
    return VERIFIER_NAME_APOSTROPHE_PATTERN.join(
        re.escape(part) for part in _NAME_APOSTROPHE.split(word)
    )
