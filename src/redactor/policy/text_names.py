"""Use row identities where corroborated and separate contextual relatives/providers."""

from redactor.policy.keys import evidence_key
from redactor.policy.names import format_person_name, person_name
from redactor.policy.normalization import normalize_name
from redactor.schemas.redaction import TextContext
from redactor.utils.constants import IDENTITY_PROVIDER, RELATIVE_NAME_NAMESPACE


def mention_name(
    value: str, context: TextContext, key: bytes, *, provider: bool
) -> str:
    normalized = normalize_name(value)
    known_name = context.provider_name if provider else context.patient_name
    identity = context.provider if provider else context.patient
    known = normalize_name(known_name).split()
    # A provider surname in an explicitly marked provider mention can refer to
    # this row's named provider. Unqualified patient surnames are not merged.
    if identity is not None and (
        normalized == " ".join(known)
        or (
            provider
            and len(normalized.split()) == 1
            and known
            and normalized == known[-1]
        )
    ):
        return format_person_name(value, identity.surrogate_name)
    scope = (
        context.patient.match.identity_key if context.patient else context.context_key
    )
    namespace = IDENTITY_PROVIDER if provider else RELATIVE_NAME_NAMESPACE
    identity_key = evidence_key(key, normalized, namespace=namespace, scope=scope)
    return person_name(identity_key, key, normalized)
