"""Compile typed column operations once, with bounded exact-value caches."""

from collections import OrderedDict
from collections.abc import Callable

from redactor.policy.tabular import assess_typed_cell, replace_typed_cell
from redactor.schemas.redaction import ColumnPolicy, TextContext
from redactor.utils.constants import (
    CONTEXT_FREE_FIELD_KINDS,
    TABULAR_CACHE_ENTRIES,
    TABULAR_CACHE_VALUE_CHARACTERS,
)


def typed_column_operations(
    policy: ColumnPolicy, key: bytes
) -> tuple[Callable[[str], bool], Callable[[str, TextContext], str]]:
    """Caches exclude identity-dependent replacements and oversized values."""
    assessments: OrderedDict[str, bool] = OrderedDict()
    replacements: OrderedDict[str, str] = OrderedDict()
    context_free = policy.kind in CONTEXT_FREE_FIELD_KINDS

    def assess(value: str) -> bool:
        if value in assessments:
            assessments.move_to_end(value)
            return assessments[value]
        required = assess_typed_cell(value, policy)
        if len(value) <= TABULAR_CACHE_VALUE_CHARACTERS:
            assessments[value] = required
            if len(assessments) > TABULAR_CACHE_ENTRIES:
                assessments.popitem(last=False)
        return required

    def replace(value: str, context: TextContext) -> str:
        if context_free and value in replacements:
            replacements.move_to_end(value)
            return replacements[value]
        output = replace_typed_cell(value, policy, context, key)
        if context_free and len(value) <= TABULAR_CACHE_VALUE_CHARACTERS:
            replacements[value] = output
            if len(replacements) > TABULAR_CACHE_ENTRIES:
                replacements.popitem(last=False)
        return output

    return assess, replace
