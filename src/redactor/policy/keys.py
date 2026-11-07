"""Keyed derivation for pseudonyms; identity resolution remains a separate step."""

import hmac
from json.encoder import encode_basestring

from redactor.utils.constants import (
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
    # This is the same compact JSON string tuple as before. Encoding its three
    # known string fields directly avoids creating a JSONEncoder for every cell.
    payload = (
        "[" + ",".join(map(encode_basestring, (namespace, scope, value))) + "]"
    ).encode(TEXT_ENCODING)
    return hmac.digest(key, PSEUDONYM_KEY_CONTEXT + payload, "sha256")


def evidence_key(key: bytes, value: str, *, namespace: str, scope: str = "") -> str:
    """Index identifying evidence without placing the original value in SQLite."""
    return derive_digest(key, value, namespace=namespace, scope=scope).hex()
