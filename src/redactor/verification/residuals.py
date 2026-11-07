"""Check whole source and output mentions against location-bound evidence."""

import re
from unicodedata import category

from redactor.inference.evidence import validate_entity_evidence
from redactor.inference.semantics import possible_entity, refine_entity
from redactor.policy.text_patterns import age_mentions, clinical_ranges
from redactor.schemas.entities import NerAdapter, TextEntities
from redactor.schemas.redaction import TextRange
from redactor.schemas.verification import ResidualCheck, ResidualCheckCollector
from redactor.utils.constants import (
    AGE_GROUP_MINIMUM,
    ENTITY_LOCATION,
    PRESERVED_US_GEOGRAPHY,
    VERIFIER_EDIT_JOIN_PATTERN,
    VERIFIER_MENTION_PREFIX_PATTERN,
    VERIFIER_MENTION_ROLE,
    VERIFIER_MENTION_SUFFIX_PATTERN,
    VERIFIER_RELATIVE_TIME_PATTERN,
    VERIFIER_ROLE_LABEL_PATTERN,
    VERIFIER_SURFACE_PUNCTUATION,
)
from redactor.utils.errors import ERROR_RESIDUAL_PHI
from redactor.verification.evidence import (
    contains_range,
    covered_by_ranges,
    sensitive_ranges,
)

_RELATIVE_TIME = re.compile(VERIFIER_RELATIVE_TIME_PATTERN)
_ROLE_LABEL = re.compile(VERIFIER_ROLE_LABEL_PATTERN)
_MENTION_ROLE = re.compile(rf"(?i){VERIFIER_MENTION_ROLE}")
_MENTION_PREFIX = re.compile(VERIFIER_MENTION_PREFIX_PATTERN)
_EDIT_JOIN = re.compile(VERIFIER_EDIT_JOIN_PATTERN)
_SURFACE_PUNCTUATION = re.compile(VERIFIER_SURFACE_PUNCTUATION)
_MENTION_SUFFIX = re.compile(VERIFIER_MENTION_SUFFIX_PATTERN)


def protected_clinical_ranges(text: str) -> tuple[TextRange, ...]:
    """The required older-age generalization is not a changed clinical dose."""
    older_ages = tuple(
        number for _, number, age in age_mentions(text) if age >= AGE_GROUP_MINIMUM
    )
    candidates = clinical_ranges(text) + tuple(
        TextRange(start=match.start(), end=match.end())
        for pattern in (_RELATIVE_TIME, _ROLE_LABEL)
        for match in pattern.finditer(text)
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
    structural: tuple[TextRange, ...] = (),
    collect: ResidualCheckCollector | None = None,
    numeric_spans: tuple[TextRange, ...] = (),
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
    allowed = exemptions + clinical + age_ranges + structural
    if collect is not None and (
        not text.strip()
        or covered_by_ranges(text, TextRange(start=0, end=len(text)), allowed)
    ):
        return
    check = ResidualCheck(
        text=text,
        statistical_text=_numeric_statistical_view(text, numeric_spans),
        exemptions=exemptions,
        allowed=allowed,
    )
    if collect is not None:
        collect(check)
        return
    verify_residual_entities(check, local_ner)


def verify_residual_entities(check: ResidualCheck, local_ner: NerAdapter) -> None:
    """Unresolved text keeps its complete context, including rewritten spans."""
    text, exemptions, allowed = check.text, check.exemptions, check.allowed
    # Do not hide edited words before inference: they can provide the context
    # needed to recognize an initial or surname that the writer left behind.
    entities = validate_entity_evidence(
        check.statistical_text,
        TextEntities(entities=local_ner(check.statistical_text)),
    )
    for observation in entities:
        # ASCII digit substitution preserves every character offset and all words.
        entity = observation.model_copy(
            update={"text": text[observation.start : observation.end]}
        )
        if not possible_entity(entity, text):
            continue
        entity = refine_entity(entity)
        if (
            entity.entity_type == ENTITY_LOCATION
            and entity.text.casefold().strip() in PRESERVED_US_GEOGRAPHY
        ):
            continue
        mention = TextRange(start=entity.start, end=entity.end)
        if not covered_by_ranges(text, mention, allowed) and not (
            _covered_name_with_role(text, mention, exemptions)
        ):
            raise ValueError(ERROR_RESIDUAL_PHI)


def _covered_name_with_role(
    text: str, mention: TextRange, exemptions: tuple[TextRange, ...]
) -> bool:
    """A prediction can cross verified edits and punctuation, never unseen words."""
    if _MENTION_ROLE.fullmatch(text[mention.start : mention.end]) and any(
        span.start >= mention.end
        and _MENTION_PREFIX.fullmatch(text[mention.start : span.start])
        for span in exemptions
    ):
        return True
    cursor = mention.start
    # Models sometimes attach a signature dash, quote or list marker to a name.
    # Only punctuation/whitespace can precede its already verified edit span;
    # even a single unedited initial must still cause rejection.
    while cursor < mention.end and (
        text[cursor].isspace() or category(text[cursor]).startswith("P")
    ):
        cursor += 1
    prefix = _MENTION_PREFIX.match(text[cursor : mention.end])
    if prefix:
        cursor += prefix.end()
    covered = False
    for span in sorted(exemptions, key=lambda value: value.start):
        if span.end <= cursor or span.start >= mention.end:
            continue
        if span.start > cursor:
            gap = text[cursor : span.start]
            if not covered or _EDIT_JOIN.fullmatch(gap) is None:
                return False
        cursor = max(cursor, span.end)
        covered = True
        if cursor >= mention.end:
            return True
    if covered and _SURFACE_PUNCTUATION.fullmatch(text[cursor : mention.end]):
        return True
    suffix = _MENTION_SUFFIX.match(text[cursor:])
    return bool(covered and suffix and cursor + suffix.end() >= mention.end)


def _numeric_statistical_view(text: str, spans: tuple[TextRange, ...]) -> str:
    """Keep lexical context intact while ignoring already verified scalar digits."""
    if not spans:
        return text
    characters = list(text)
    for span in spans:
        for index in range(span.start, span.end):
            if "0" <= characters[index] <= "9":
                characters[index] = "0"
    return "".join(characters)
