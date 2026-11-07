"""Reject impossible typed predictions without treating uncertainty as clean."""

import re
from unicodedata import normalize

from redactor.policy.text_patterns import age_mentions
from redactor.schemas.entities import TextEntity
from redactor.utils.constants import (
    ENTITY_AGE,
    ENTITY_DATE,
    ENTITY_LOCATION,
    ENTITY_PERSON,
    ENTITY_TIME,
    NAME_TITLES,
    NAME_TRAILING_VERB_PATTERN,
    NER_DATE_WORD_PATTERN,
    NER_DIGIT_CUE_PATTERN,
    NER_EMAIL_CUE_PATTERN,
    NER_EMAIL_LABEL,
    NER_IP_CUE_PATTERN,
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
    VERIFIER_MENTION_PREFIX_PATTERN,
    ZIP_CODE_PATTERN,
)

_NUMBER_WORD = re.compile(NER_NUMBER_WORD_PATTERN)
_OLDER_AGE_WORD = re.compile(NER_OLDER_AGE_WORD_PATTERN)
_NON_IDENTIFYING_ROLE = re.compile(NON_IDENTIFYING_ROLE_PATTERN)
_NON_IDENTIFYING_LOCATION = re.compile(NON_IDENTIFYING_LOCATION_PATTERN)
_ZIP_CODE = re.compile(ZIP_CODE_PATTERN)
_EMAIL_CUE = re.compile(NER_EMAIL_CUE_PATTERN)
_IP_CUE = re.compile(NER_IP_CUE_PATTERN)
_URL_CUE = re.compile(NER_URL_CUE_PATTERN)
_TIME_WORD = re.compile(NER_TIME_WORD_PATTERN)
_DATE_WORD = re.compile(NER_DATE_WORD_PATTERN)
_TRAILING_VERB = re.compile(NAME_TRAILING_VERB_PATTERN)
_MENTION_PREFIX = re.compile(VERIFIER_MENTION_PREFIX_PATTERN)
_NUMBER_CUE_PATTERNS = tuple(
    re.compile(pattern)
    for pattern in (
        NER_DIGIT_CUE_PATTERN,
        NER_NUMBER_WORD_PATTERN,
        NER_DATE_WORD_PATTERN,
        NER_TIME_WORD_PATTERN,
        NER_OLDER_AGE_WORD_PATTERN,
    )
)


def possible_entity(entity: TextEntity, text: str | None = None) -> bool:
    """An alphabetic label cannot be an IP, phone or numeric time.

    Digits, spelled-out numbers and obfuscated contact syntax remain candidates,
    even when their exact format is unsupported. This does not validate a value
    or authorize leaving an identifier unedited.
    """
    value = normalize(UNICODE_NORMAL_FORM, entity.text)
    numeric = any(character.isdecimal() for character in value) or bool(
        _NUMBER_WORD.search(value)
    )
    if (
        text is not None
        and (
            entity.entity_type in (ENTITY_AGE, ENTITY_DATE, ENTITY_TIME)
            or entity.label
            in (*NER_NUMERIC_IDENTIFIER_LABELS, NER_PHONE_LABEL, NER_IP_LABEL)
        )
        and _numbers_belong_to_explicit_ages(entity, text)
    ):
        # "Age 12" cannot also be a phone, licence, date or clock value. The
        # deterministic age policy still handles 90+, and the remaining text
        # stays visible to independent name/contact checks.
        return False
    if entity.entity_type == ENTITY_AGE:
        return numeric or bool(_OLDER_AGE_WORD.search(value))
    if entity.entity_type == ENTITY_PERSON and (
        _NON_IDENTIFYING_ROLE.fullmatch(value)
        or value.strip().casefold().removesuffix(".") in NAME_TITLES
    ):
        return False
    if entity.entity_type == ENTITY_LOCATION and text is not None:
        if any(
            match.start() <= entity.start and entity.end <= match.end()
            for match in _NON_IDENTIFYING_LOCATION.finditer(text)
        ):
            return False
    if entity.label == NER_PHONE_LABEL:
        return numeric
    if entity.label in NER_NUMERIC_IDENTIFIER_LABELS:
        return numeric
    if entity.label == NER_ZIP_LABEL:
        return _ZIP_CODE.fullmatch(value) is not None
    if entity.label == NER_EMAIL_LABEL:
        return bool(_EMAIL_CUE.search(value))
    if entity.label == NER_IP_LABEL:
        return bool(_IP_CUE.search(value))
    if entity.label == NER_URL_LABEL:
        return any(character.isalnum() for character in value) and bool(
            _URL_CUE.search(value)
        )
    if entity.entity_type == ENTITY_TIME:
        return numeric or bool(_TIME_WORD.search(value))
    if entity.entity_type == ENTITY_DATE:
        return numeric or bool(_DATE_WORD.search(value))
    return True


def refine_entity(entity: TextEntity) -> TextEntity:
    """Trim grammatical context only when its datatype boundary is explicit."""
    if entity.entity_type != ENTITY_PERSON:
        return entity
    suffix = _TRAILING_VERB.search(entity.text)
    if suffix is None:
        return entity
    name = entity.text[: suffix.start()]
    # A role is context, not the first component of a person's name.
    prefix = _MENTION_PREFIX.match(name)
    words = name[prefix.end() if prefix else 0 :].split()
    if not words or not (words[0][0].isupper() and words[-1][0].isupper()):
        return entity
    return entity.model_copy(update={"text": name, "end": entity.start + len(name)})


def _numbers_belong_to_explicit_ages(entity: TextEntity, text: str) -> bool:
    ages = age_mentions(text)
    if not ages:
        return False
    cues = tuple(
        (entity.start + match.start(), entity.start + match.end())
        for pattern in _NUMBER_CUE_PATTERNS
        for match in pattern.finditer(entity.text)
    )
    return bool(cues) and all(
        any(
            expression.start <= start < end <= expression.end
            for expression, _, _ in ages
        )
        for start, end in cues
    )
