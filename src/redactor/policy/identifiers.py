"""Stable typed identifiers; generated values are claims for later verification."""

import re
from uuid import UUID

from redactor.policy.keys import derive_digest
from redactor.policy.normalization import normalize_digits, normalize_identifier
from redactor.utils.constants import (
    DOCX_CUSTOM_XML_ITEM_ID_NAMESPACE,
    IDENTIFIER_DIGITS,
    NPI_BASE_DIGITS,
    NPI_LUHN_PREFIX_SUM,
    NPI_NAMESPACE,
    NPI_PREFIX_CHOICES,
    PRODUCT_LOT_NAMESPACE,
    SHORT_IDENTIFIER_DIGITS,
    SHORT_IDENTIFIER_NAMESPACES,
    SSN_AREA_LIMIT,
    SSN_DIGITS,
    SSN_DISALLOWED_AREA,
    SSN_NAMESPACE,
    UUID_BYTES,
    UUID_PATTERN,
    UUID_VERSION,
)
from redactor.utils.errors import ERROR_IDENTIFIER, ERROR_REPLACEMENT_COLLISION

_UUID_VALUE = re.compile(UUID_PATTERN)


def replace_identifier(
    value: str, key: bytes, *, namespace: str, scope: str = ""
) -> str:
    """Use a larger decimal space instead of truncating a hash to a short MRN."""
    if namespace == DOCX_CUSTOM_XML_ITEM_ID_NAMESPACE:
        return _replace_uuid(value, key, namespace=namespace, scope=scope)
    canonical = normalize_identifier(value)
    digest = derive_digest(key, canonical, namespace=namespace, scope=scope)
    digits = (
        SHORT_IDENTIFIER_DIGITS
        if namespace in SHORT_IDENTIFIER_NAMESPACES
        else IDENTIFIER_DIGITS
    )
    number = int.from_bytes(digest, "big") % (10**digits)
    surrogate = f"{number:0{digits}d}"
    if surrogate == canonical:
        raise ValueError(ERROR_REPLACEMENT_COLLISION)
    return surrogate


def canonical_uuid(value: str) -> str:
    """Accept one complete GUID, with paired optional braces and no extra text."""
    if _UUID_VALUE.fullmatch(value) is None:
        raise ValueError(ERROR_IDENTIFIER)
    return str(UUID(value))


def _replace_uuid(value: str, key: bytes, *, namespace: str, scope: str) -> str:
    canonical = canonical_uuid(value)
    digest = derive_digest(key, canonical, namespace=namespace, scope=scope)
    surrogate = str(UUID(bytes=digest[:UUID_BYTES], version=UUID_VERSION))
    if surrogate == canonical:
        raise ValueError(ERROR_REPLACEMENT_COLLISION)
    if value.isupper():
        surrogate = surrogate.upper()
    return "{" + surrogate + "}" if value.startswith("{") else surrogate


def replace_lot(value: str, key: bytes, *, scope: str = "") -> str:
    return replace_identifier(value, key, namespace=PRODUCT_LOT_NAMESPACE, scope=scope)


def replace_npi(value: str, key: bytes) -> str:
    """Create a ten-digit NPI with the CMS Luhn check digit in the provider space.

    Input identifiers need not already have a valid checksum: synthetic or dirty
    identifiers still need pseudonymization. Invalid lengths remain unassessed.
    """
    canonical = normalize_digits(value)
    if len(canonical) != NPI_BASE_DIGITS + 1:
        raise ValueError(ERROR_IDENTIFIER)
    digest = derive_digest(key, canonical, namespace=NPI_NAMESPACE)
    suffix_space = 10 ** (NPI_BASE_DIGITS - 1)
    number = int.from_bytes(digest, "big") % (len(NPI_PREFIX_CHOICES) * suffix_space)
    prefix_index, suffix = divmod(number, suffix_space)
    root = f"{NPI_PREFIX_CHOICES[prefix_index]}{suffix:0{NPI_BASE_DIGITS - 1}d}"
    surrogate = root + npi_check_digit(root)
    if surrogate == canonical:
        raise ValueError(ERROR_REPLACEMENT_COLLISION)
    return surrogate


def npi_check_digit(root: str) -> str:
    """CMS adds 24 for the implicit 80840 prefix before applying Luhn."""
    if len(root) != NPI_BASE_DIGITS or not root.isascii() or not root.isdigit():
        raise ValueError(ERROR_IDENTIFIER)
    total = NPI_LUHN_PREFIX_SUM
    for position, digit in enumerate(reversed(root)):
        number = int(digit) * (2 if position % 2 == 0 else 1)
        total += number // 10 + number % 10
    return str((-total) % 10)


def replace_ssn(value: str, key: bytes) -> str:
    canonical = normalize_digits(value)
    if len(canonical) != SSN_DIGITS:
        raise ValueError(ERROR_IDENTIFIER)
    digest = derive_digest(key, canonical, namespace=SSN_NAMESPACE)
    number = int.from_bytes(digest, "big")
    area = number % (SSN_AREA_LIMIT - 1) + 1
    if area >= SSN_DISALLOWED_AREA:
        area += 1
    group = (number // SSN_AREA_LIMIT) % 99 + 1
    serial = (number // (SSN_AREA_LIMIT * 99)) % 9999 + 1
    result = f"{area:03d}-{group:02d}-{serial:04d}"
    if normalize_digits(result) == canonical:
        raise ValueError(ERROR_REPLACEMENT_COLLISION)
    return result
