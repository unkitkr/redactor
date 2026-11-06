"""Produce keyed, non-routable network-address surrogates."""

from ipaddress import IPv4Address, IPv6Address, ip_address

from redactor.policy.identifiers import replace_identifier
from redactor.policy.keys import derive_digest
from redactor.utils.constants import (
    NETWORK_NAMESPACE,
    SURROGATE_WEB_TEMPLATE,
    WEB_NAMESPACE,
)
from redactor.utils.errors import ERROR_REPLACEMENT_COLLISION


def replace_network_address(value: str, key: bytes) -> str:
    original = ip_address(value)
    digest = derive_digest(key, original.compressed, namespace=NETWORK_NAMESPACE)
    if isinstance(original, IPv4Address):
        # RFC 1918 private address space, never a public patient network.
        result = str(IPv4Address(bytes((10, *digest[:3]))))
    else:
        # RFC 4193 local address space.
        result = str(IPv6Address(bytes((0xFD, *digest[:15]))))
    if result == original.compressed:
        raise ValueError(ERROR_REPLACEMENT_COLLISION)
    return result


def replace_web_address(value: str, key: bytes) -> str:
    return SURROGATE_WEB_TEMPLATE.format(
        identifier=replace_identifier(value, key, namespace=WEB_NAMESPACE)
    )
