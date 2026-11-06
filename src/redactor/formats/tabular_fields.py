"""Recognize column semantics, preserving all columns and validating clinical values."""

import re

from redactor.schemas.redaction import ColumnPolicy
from redactor.utils.constants import (
    CLINICAL_CODE_SEPARATOR_PATTERN,
    CLINICAL_FIELD_PATTERNS,
    FIELD_TEXT,
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
