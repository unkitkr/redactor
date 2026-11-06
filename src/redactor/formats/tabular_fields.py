"""Recognize column semantics, preserving all columns and validating clinical values."""

import re

from redactor.schemas.redaction import ColumnPolicy
from redactor.utils.constants import (
    CLINICAL_CODE_SEPARATOR_PATTERN,
    CLINICAL_FIELD_PATTERNS,
    FIELD_TEXT,
    HL7_RELATIONSHIP_DISPLAYS,
    KINSHIP_DISPLAY_NAMESPACE,
    LAB_DESCRIPTION_NAMESPACE,
    LAB_DESCRIPTION_TERMS,
    TABULAR_FIELD_ALIASES,
)
from redactor.utils.errors import ERROR_CLINICAL_CHANGED


def column_policies(columns: tuple[str, ...]) -> tuple[ColumnPolicy, ...]:
    aliases = {
        alias: (kind, namespace)
        for kind, namespace, names in TABULAR_FIELD_ALIASES
        for alias in names
    }
    policies: list[ColumnPolicy] = []
    for index, column in enumerate(columns):
        normalized = re.sub(r"[\s-]+", "_", column.strip().casefold())
        kind, namespace = aliases.get(normalized, (FIELD_TEXT, ""))
        policies.append(ColumnPolicy(index=index, kind=kind, namespace=namespace))
    return tuple(policies)


def validate_clinical_field(value: str, namespace: str) -> None:
    if not value.strip():
        return
    if namespace.startswith(KINSHIP_DISPLAY_NAMESPACE):
        code = namespace.removeprefix(KINSHIP_DISPLAY_NAMESPACE)
        expected = dict(HL7_RELATIONSHIP_DISPLAYS).get(code)
        if (
            expected is None
            or " ".join(value.split()).casefold() != expected.casefold()
        ):
            raise ValueError(ERROR_CLINICAL_CHANGED)
        return
    if namespace == LAB_DESCRIPTION_NAMESPACE:
        tokens = re.findall(r"[A-Za-z0-9]+|[^A-Za-z0-9\s./\[\]()-]", value.casefold())
        if not tokens or any(token not in LAB_DESCRIPTION_TERMS for token in tokens):
            raise ValueError(ERROR_CLINICAL_CHANGED)
        return
    patterns = dict(CLINICAL_FIELD_PATTERNS)
    pattern = patterns.get(namespace)
    if pattern is None:
        raise ValueError(ERROR_CLINICAL_CHANGED)
    if namespace == "application":
        if re.fullmatch(pattern, value) is None:
            raise ValueError(ERROR_CLINICAL_CHANGED)
        return
    for token in re.split(CLINICAL_CODE_SEPARATOR_PATTERN, value.strip()):
        if re.fullmatch(pattern, token, flags=re.IGNORECASE) is None:
            raise ValueError(ERROR_CLINICAL_CHANGED)
