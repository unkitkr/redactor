"""Use row identities where corroborated and separate contextual relatives/providers."""

from redactor.policy.keys import evidence_key
from redactor.policy.name_matching import compatible_name_spelling
from redactor.policy.names import format_person_name, person_name
from redactor.policy.normalization import normalize_name
from redactor.schemas.redaction import TextContext
from redactor.utils.constants import IDENTITY_PROVIDER, RELATIVE_NAME_NAMESPACE


def mention_name(
    value: str,
    context: TextContext,
    key: bytes,
    *,
    provider: bool,
    relative: bool = False,
) -> str:
    normalized = normalize_name(value)
    known_name = context.provider_name if provider else context.patient_name
    identity = context.provider if provider else context.patient
    known = normalize_name(known_name).split()
    # Classification establishes this record's role before applying a spelling.
    # This is local mention resolution, never a name-only global identity merge.
    if (
        not relative
        and identity is not None
        and (
            compatible_name_spelling(value, known_name, allow_surname=True)
            or (
                provider
                and len(normalized.split()) == 1
                and known
                and normalized == known[-1]
            )
        )
    ):
        return format_person_name(
            value, identity.surrogate_name, known_original=known_name
        )
    scope = (
        context.patient.match.identity_key if context.patient else context.context_key
    )
    namespace = IDENTITY_PROVIDER if provider else RELATIVE_NAME_NAMESPACE
    identity_key = evidence_key(key, normalized, namespace=namespace, scope=scope)
    surrogate = person_name(identity_key, key, normalized)
    # One-word mentions keep a one-word surrogate of the same shape.
    return surrogate if len(normalized.split()) > 1 else surrogate.split()[0]
