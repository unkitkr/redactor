"""Check whole source and output mentions against location-bound evidence."""

import re

from redactor.inference.evidence import validate_entity_evidence
from redactor.policy.text_patterns import age_mentions, clinical_ranges
from redactor.schemas.entities import NerAdapter, TextEntities
from redactor.schemas.redaction import TextRange
from redactor.utils.constants import (
    AGE_GROUP_MINIMUM,
    VERIFIER_MENTION_PREFIX_PATTERN,
    VERIFIER_MENTION_SUFFIX_PATTERN,
    VERIFIER_RELATIVE_TIME_PATTERN,
    VERIFIER_ROLE_LABEL_PATTERN,
)
from redactor.utils.errors import ERROR_RESIDUAL_PHI
from redactor.verification.evidence import contains_range, sensitive_ranges


def protected_clinical_ranges(text: str) -> tuple[TextRange, ...]:
    """The required older-age generalization is not a changed clinical dose."""
    older_ages = tuple(
        number for _, number, age in age_mentions(text) if age >= AGE_GROUP_MINIMUM
    )
    candidates = clinical_ranges(text) + tuple(
        TextRange(start=match.start(), end=match.end())
        for pattern in (VERIFIER_RELATIVE_TIME_PATTERN, VERIFIER_ROLE_LABEL_PATTERN)
        for match in re.finditer(pattern, text)
    )
    return tuple(
        span
        for span in candidates
        if not any(span.start < age.end and age.start < span.end for age in older_ages)
    )


def assessed_age_ranges(text: str) -> tuple[TextRange, ...]:
    return tuple(
        TextRange(
            start=expression.start,
            end=expression.end + int(text[expression.end : expression.end + 1] == "+"),
        )
        for expression, _, _ in age_mentions(text)
    )


def scan_residuals(
    text: str,
    exemptions: tuple[TextRange, ...],
    local_ner: NerAdapter,
    *,
    patient_name: str = "",
    provider_name: str = "",
    clinical: tuple[TextRange, ...] | None = None,
    assessed_ages: tuple[TextRange, ...] | None = None,
) -> None:
    clinical = protected_clinical_ranges(text) if clinical is None else clinical
    for mention in sensitive_ranges(
        text, clinical, patient_name=patient_name, provider_name=provider_name
    ):
        if not any(contains_range(span, mention) for span in exemptions):
            raise ValueError(ERROR_RESIDUAL_PHI)
    ages = age_mentions(text)
    for _, number, age in ages:
        if age == AGE_GROUP_MINIMUM and text[number.end : number.end + 1] == "+":
            continue
        if age >= AGE_GROUP_MINIMUM and not any(
            contains_range(span, number) for span in exemptions
        ):
            raise ValueError(ERROR_RESIDUAL_PHI)
    age_ranges = assessed_age_ranges(text) if assessed_ages is None else assessed_ages
    allowed = exemptions + clinical + age_ranges
    # Do not hide edited words before inference: they can provide the context
    # needed to recognize an initial or surname that the writer left behind.
    entities = validate_entity_evidence(text, TextEntities(entities=local_ner(text)))
    for entity in entities:
        mention = TextRange(start=entity.start, end=entity.end)
        if not any(contains_range(span, mention) for span in allowed) and not (
            _covered_name_with_role(text, mention, exemptions)
        ):
            raise ValueError(ERROR_RESIDUAL_PHI)


def _covered_name_with_role(
    text: str, mention: TextRange, exemptions: tuple[TextRange, ...]
) -> bool:
    """NER may include a role label; no unedited name fragment is exempted."""
    for span in exemptions:
        if not contains_range(mention, span):
            continue
        prefix = text[mention.start : span.start]
        if prefix and re.fullmatch(VERIFIER_MENTION_PREFIX_PATTERN, prefix) is None:
            continue
        if mention.end == span.end:
            return True
        suffix = re.match(VERIFIER_MENTION_SUFFIX_PATTERN, text[span.end :])
        if suffix is not None and span.end + suffix.end() >= mention.end:
            return True
    return False
