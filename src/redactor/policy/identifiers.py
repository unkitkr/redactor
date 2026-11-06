"""Stable typed identifiers; generated values are claims for later verification."""

from redactor.policy.keys import derive_digest
from redactor.policy.normalization import normalize_digits, normalize_identifier
from redactor.utils.constants import (
    IDENTIFIER_DIGITS,
    NPI_BASE_DIGITS,
    NPI_LUHN_PREFIX_SUM,
    NPI_NAMESPACE,
    NPI_PREFIX_CHOICES,
    PRODUCT_LOT_NAMESPACE,
)
from redactor.utils.errors import ERROR_IDENTIFIER, ERROR_REPLACEMENT_COLLISION


def replace_identifier(
    value: str, key: bytes, *, namespace: str, scope: str = ""
) -> str:
    """Use a larger decimal space instead of truncating a hash to a short MRN."""
    canonical = normalize_identifier(value)
    digest = derive_digest(key, canonical, namespace=namespace, scope=scope)
    number = int.from_bytes(digest, "big") % (10**IDENTIFIER_DIGITS)
    surrogate = f"{number:0{IDENTIFIER_DIGITS}d}"
    if surrogate == canonical:
        raise ValueError(ERROR_REPLACEMENT_COLLISION)
    return surrogate


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
