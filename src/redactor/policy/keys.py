"""Keyed derivation for pseudonyms; identity resolution remains a separate step."""

import hmac
import json

from redactor.utils.constants import (
    JSON_SEPARATORS,
    PSEUDONYM_KEY_CONTEXT,
    SECRET_KEY_BYTES,
    TEXT_ENCODING,
)
from redactor.utils.errors import ERROR_IDENTIFIER, ERROR_MAPPING_KEY


def derive_digest(key: bytes, value: str, *, namespace: str, scope: str = "") -> bytes:
    """Length-delimited inputs keep roles, identifier kinds and issuers separate."""
    if len(key) != SECRET_KEY_BYTES:
        raise ValueError(ERROR_MAPPING_KEY)
    if not value or not namespace:
        raise ValueError(ERROR_IDENTIFIER)
    payload = json.dumps(
        (namespace, scope, value), separators=JSON_SEPARATORS, ensure_ascii=False
    ).encode(TEXT_ENCODING)
    return hmac.digest(key, PSEUDONYM_KEY_CONTEXT + payload, "sha256")


def evidence_key(key: bytes, value: str, *, namespace: str, scope: str = "") -> str:
    """Index identifying evidence without placing the original value in SQLite."""
    return derive_digest(key, value, namespace=namespace, scope=scope).hex()
