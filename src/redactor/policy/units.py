"""Validate supported clinical unit expressions without changing their spelling."""

import re

from redactor.utils.constants import (
    CLINICAL_UNIT_ALIASES,
    CLINICAL_UNIT_ATOMS,
    CLINICAL_UNIT_MAX_LENGTH,
    CLINICAL_UNIT_METRIC_ATOMS,
    CLINICAL_UNIT_PREFIXES,
)


def is_clinical_unit(value: str) -> bool:
    """Accept known symbols, powers, products and ratios, never arbitrary words.

    This is a bounded medical subset of UCUM, not a conversion engine. Arbitrary
    annotations are deliberately excluded because they can contain identifiers.
    Human-readable aliases are used only for validation; saved bytes stay exact.
    """
    text = value.strip().replace("µ", "u").replace("μ", "u")
    text = dict(CLINICAL_UNIT_ALIASES).get(text, text)
    if not text or len(text) > CLINICAL_UNIT_MAX_LENGTH:
        return False
    atoms = set(CLINICAL_UNIT_ATOMS) | set(CLINICAL_UNIT_METRIC_ATOMS)
    atoms.update(
        prefix + atom
        for prefix in CLINICAL_UNIT_PREFIXES
        for atom in CLINICAL_UNIT_METRIC_ATOMS
    )
    symbols = "|".join(re.escape(atom) for atom in sorted(atoms, key=len, reverse=True))
    component = re.compile(rf"(?:{symbols})(?:\^?[+-]?[0-9]+)?|[1-9][0-9]*")
    position = 0
    depth = 0
    needs_component = True
    while position < len(text):
        character = text[position]
        if character == "(" and needs_component:
            depth += 1
        elif character == ")" and not needs_component and depth:
            depth -= 1
        elif character in "./" and not needs_component:
            needs_component = True
        elif character == "/" and position == 0:
            pass  # UCUM permits an implicit numerator of one.
        elif needs_component:
            match = component.match(text, position)
            if match is None:
                return False
            position = match.end()
            needs_component = False
            continue
        else:
            return False
        position += 1
    return not needs_component and depth == 0
