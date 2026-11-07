"""Typed contact replacements; unsupported shapes fail instead of losing digits."""

import re
import unicodedata

from redactor.policy.keys import derive_digest
from redactor.policy.normalization import normalize_digits
from redactor.utils.constants import (
    ADDRESS_NAMESPACE,
    EMAIL_NAMESPACE,
    NANP_COUNTRY_CODE,
    NANP_MINIMUM_PREFIX,
    NANP_NUMBER_BLOCK,
    NANP_PHONE_DIGITS,
    PHONE_LINE_NUMBER_SPACE,
    PHONE_NAMESPACE,
    SURROGATE_DOMAIN,
    SURROGATE_FAMILY_PREFIXES,
    SURROGATE_FAMILY_SUFFIXES,
    SURROGATE_STREET_NUMBER_MINIMUM,
    SURROGATE_STREET_NUMBER_SPACE,
    SURROGATE_STREET_SUFFIX,
    UNICODE_NORMAL_FORM,
)
from redactor.utils.errors import ERROR_IDENTIFIER, ERROR_REPLACEMENT_COLLISION

_EMAIL_ADDRESS = re.compile(r"[^\s@]+@[^\s@]+\.[^\s@]+")


def canonical_phone(value: str) -> str:
    normalized = unicodedata.normalize(UNICODE_NORMAL_FORM, value).strip()
    digits = normalize_digits(value)
    # A foreign number can have ten digits too. Its country prefix must never
    # be interpreted as a domestic area code merely because the length fits.
    if normalized.startswith("+") and not digits.startswith(NANP_COUNTRY_CODE):
        raise ValueError(ERROR_IDENTIFIER)
    if len(digits) == NANP_PHONE_DIGITS + 1 and digits.startswith(NANP_COUNTRY_CODE):
        digits = digits[1:]
    if len(digits) != NANP_PHONE_DIGITS or digits[0] not in "23456789":
        raise ValueError(ERROR_IDENTIFIER)
    return digits


def replace_phone(value: str, key: bytes) -> str:
    canonical = canonical_phone(value)
    number = int.from_bytes(
        derive_digest(key, canonical, namespace=PHONE_NAMESPACE), "big"
    )
    number, line = divmod(number, PHONE_LINE_NUMBER_SPACE)
    number, exchange = divmod(number, NANP_NUMBER_BLOCK)
    area = number % NANP_NUMBER_BLOCK + NANP_MINIMUM_PREFIX
    exchange += NANP_MINIMUM_PREFIX
    # N11 prefixes are service numbers rather than ordinary NANP prefixes.
    area += int(area % 100 == 11)
    exchange += int(exchange % 100 == 11)
    surrogate = f"{area:03d}{exchange:03d}{line:04d}"
    if surrogate == canonical:
        raise ValueError(ERROR_REPLACEMENT_COLLISION)
    original_digits = normalize_digits(value)
    if len(original_digits) > NANP_PHONE_DIGITS:
        surrogate = NANP_COUNTRY_CODE + surrogate
    digits = iter(surrogate)
    return "".join(
        next(digits) if char.isascii() and char.isdigit() else char
        for char in unicodedata.normalize(UNICODE_NORMAL_FORM, value)
    )


def replace_email(value: str, key: bytes) -> str:
    if _EMAIL_ADDRESS.fullmatch(value) is None:
        raise ValueError(ERROR_IDENTIFIER)
    digest = derive_digest(key, value.casefold(), namespace=EMAIL_NAMESPACE)
    return f"user{digest.hex()[:24]}@{SURROGATE_DOMAIN}"


def replace_street(value: str, key: bytes) -> str:
    canonical = " ".join(value.casefold().split())
    number = int.from_bytes(
        derive_digest(key, canonical, namespace=ADDRESS_NAMESPACE), "big"
    )
    number, house = divmod(number, SURROGATE_STREET_NUMBER_SPACE)
    number, prefix = divmod(number, len(SURROGATE_FAMILY_PREFIXES))
    suffix = number % len(SURROGATE_FAMILY_SUFFIXES)
    street = SURROGATE_FAMILY_PREFIXES[prefix] + SURROGATE_FAMILY_SUFFIXES[suffix]
    return (
        f"{house + SURROGATE_STREET_NUMBER_MINIMUM} {street} {SURROGATE_STREET_SUFFIX}"
    )
