"""Authenticated, context-bound encryption for bounded private evidence records."""

import hmac
import os

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from redactor.utils.constants import (
    ENCRYPTION_HEADER,
    ENCRYPTION_KEY_CONTEXT,
    ENCRYPTION_NONCE_BYTES,
    ENCRYPTION_TAG_BYTES,
    MAX_PRIVATE_RECORD_BYTES,
    SECRET_KEY_BYTES,
)
from redactor.utils.errors import ERROR_PRIVATE_RECORD


def encrypt_payload(key: bytes, payload: bytes, *, context: bytes) -> bytes:
    """Each record has a separate derived key and a fresh random 96-bit nonce."""
    if len(payload) > MAX_PRIVATE_RECORD_BYTES:
        raise ValueError(ERROR_PRIVATE_RECORD)
    encryption_key = _record_key(key, context)
    nonce = os.urandom(ENCRYPTION_NONCE_BYTES)
    ciphertext = AESGCM(encryption_key).encrypt(nonce, payload, context)
    return ENCRYPTION_HEADER + nonce + ciphertext


def decrypt_payload(key: bytes, envelope: bytes, *, context: bytes) -> bytes:
    """Wrong keys, altered bytes and evidence moved to another context all fail."""
    minimum_size = (
        len(ENCRYPTION_HEADER) + ENCRYPTION_NONCE_BYTES + ENCRYPTION_TAG_BYTES
    )
    if (
        not envelope.startswith(ENCRYPTION_HEADER)
        or len(envelope) < minimum_size
        or len(envelope) > minimum_size + MAX_PRIVATE_RECORD_BYTES
    ):
        raise ValueError(ERROR_PRIVATE_RECORD)
    encryption_key = _record_key(key, context)
    nonce_end = len(ENCRYPTION_HEADER) + ENCRYPTION_NONCE_BYTES
    nonce = envelope[len(ENCRYPTION_HEADER) : nonce_end]
    try:
        return AESGCM(encryption_key).decrypt(nonce, envelope[nonce_end:], context)
    except (InvalidTag, ValueError):
        raise ValueError(ERROR_PRIVATE_RECORD) from None


def _record_key(key: bytes, context: bytes) -> bytes:
    if len(key) != SECRET_KEY_BYTES or not context:
        raise ValueError(ERROR_PRIVATE_RECORD)
    return hmac.digest(key, ENCRYPTION_KEY_CONTEXT + context, "sha256")
