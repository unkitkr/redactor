"""Generate stable person names from resolved identities, with no source-name table."""

from redactor.policy.keys import derive_digest
from redactor.policy.normalization import normalize_name
from redactor.utils.constants import (
    PERSON_NAME_NAMESPACE,
    SURROGATE_FAMILY_PREFIXES,
    SURROGATE_FAMILY_SUFFIXES,
    SURROGATE_GIVEN_NAMES,
)
from redactor.utils.errors import ERROR_REPLACEMENT_COLLISION


def person_name(identity_key: str, key: bytes, original_name: str = "") -> str:
    digest = derive_digest(key, identity_key, namespace=PERSON_NAME_NAMESPACE)
    number = int.from_bytes(digest, "big")
    surname_space = len(SURROGATE_FAMILY_PREFIXES) * len(SURROGATE_FAMILY_SUFFIXES)
    vocabulary_size = len(SURROGATE_GIVEN_NAMES) * surname_space
    original_words = set(normalize_name(original_name).split())
    # Avoid preserving a source component. The frozen cohort supplies the same
    # canonical name for full-name and abbreviated mentions of this identity.
    for offset in range(vocabulary_size):
        given_index, family_index = divmod(
            (number + offset) % vocabulary_size, surname_space
        )
        prefix_index, suffix_index = divmod(
            family_index, len(SURROGATE_FAMILY_SUFFIXES)
        )
        given = SURROGATE_GIVEN_NAMES[given_index]
        family = (
            SURROGATE_FAMILY_PREFIXES[prefix_index]
            + SURROGATE_FAMILY_SUFFIXES[suffix_index]
        )
        if (
            given.casefold() not in original_words
            and family.casefold() not in original_words
        ):
            return f"{given} {family}"
    raise ValueError(ERROR_REPLACEMENT_COLLISION)


def format_person_name(original: str, surrogate: str) -> str:
    """Preserve common display forms without guessing uncorroborated identities."""
    given, family = surrogate.split(maxsplit=1)
    if "^" in original:
        parts = original.split("^")
        parts[0] = family
        if len(parts) > 1:
            parts[1] = given
        return "^".join(parts[:2] + ["" for _ in parts[2:]])
    if "," in original:
        return f"{family}, {given}"
    return surrogate
