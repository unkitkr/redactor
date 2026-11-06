"""Reject impossible typed predictions without treating uncertainty as clean."""

import re
from unicodedata import normalize

from redactor.schemas.entities import TextEntity
from redactor.utils.constants import (
    ENTITY_AGE,
    ENTITY_DATE,
    ENTITY_LOCATION,
    ENTITY_PERSON,
    ENTITY_TIME,
    NAME_TRAILING_VERB_PATTERN,
    NER_DATE_WORD_PATTERN,
    NER_EMAIL_CUE_PATTERN,
    NER_EMAIL_LABEL,
    NER_IP_LABEL,
    NER_NUMBER_WORD_PATTERN,
    NER_NUMERIC_IDENTIFIER_LABELS,
    NER_OLDER_AGE_WORD_PATTERN,
    NER_PHONE_LABEL,
    NER_TIME_WORD_PATTERN,
    NER_URL_CUE_PATTERN,
    NER_URL_LABEL,
    NER_ZIP_LABEL,
    NON_IDENTIFYING_LOCATION_PATTERN,
    NON_IDENTIFYING_ROLE_PATTERN,
    UNICODE_NORMAL_FORM,
    ZIP_CODE_PATTERN,
)


def possible_entity(entity: TextEntity, text: str | None = None) -> bool:
    """An alphabetic label cannot be an IP, phone or numeric time.

    Digits, spelled-out numbers and obfuscated contact syntax remain candidates,
    even when their exact format is unsupported. This does not validate a value
    or authorize leaving an identifier unedited.
    """
    value = normalize(UNICODE_NORMAL_FORM, entity.text)
    numeric = any(character.isdecimal() for character in value) or bool(
        re.search(NER_NUMBER_WORD_PATTERN, value)
    )
    if entity.entity_type == ENTITY_AGE:
        return numeric or bool(re.search(NER_OLDER_AGE_WORD_PATTERN, value))
    if entity.entity_type == ENTITY_PERSON and re.fullmatch(
        NON_IDENTIFYING_ROLE_PATTERN, value
    ):
        return False
    if entity.entity_type == ENTITY_LOCATION and text is not None:
        if any(
            match.start() <= entity.start and entity.end <= match.end()
            for match in re.finditer(NON_IDENTIFYING_LOCATION_PATTERN, text)
        ):
            return False
    if entity.label == NER_PHONE_LABEL:
        return numeric
    if entity.label in NER_NUMERIC_IDENTIFIER_LABELS:
        return numeric
    if entity.label == NER_ZIP_LABEL:
        return re.fullmatch(ZIP_CODE_PATTERN, value) is not None
    if entity.label == NER_EMAIL_LABEL:
        return bool(re.search(NER_EMAIL_CUE_PATTERN, value))
    if entity.label == NER_IP_LABEL:
        return numeric or ":" in value or "." in value
    if entity.label == NER_URL_LABEL:
        return any(character.isalnum() for character in value) and bool(
            re.search(NER_URL_CUE_PATTERN, value)
        )
    if entity.entity_type == ENTITY_TIME:
        return numeric or bool(re.search(NER_TIME_WORD_PATTERN, value))
    if entity.entity_type == ENTITY_DATE:
        return numeric or bool(re.search(NER_DATE_WORD_PATTERN, value))
    return True


def refine_entity(entity: TextEntity) -> TextEntity:
    """Keep a trailing narrative verb out of a model's full-name span."""
    if entity.entity_type != ENTITY_PERSON:
        return entity
    suffix = re.search(NAME_TRAILING_VERB_PATTERN, entity.text)
    if suffix is None:
        return entity
    name = entity.text[: suffix.start()]
    words = name.split()
    if len(words) < 2 or not (words[0][0].isupper() and words[-1][0].isupper()):
        return entity
    return entity.model_copy(update={"text": name, "end": entity.start + len(name)})
