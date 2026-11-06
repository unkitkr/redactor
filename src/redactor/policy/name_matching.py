"""Compare name spelling within an already established record context."""

from redactor.policy.normalization import normalize_name


def compatible_name_spelling(
    left: str, right: str, *, allow_surname: bool = False
) -> bool:
    first, second = normalize_name(left).split(), normalize_name(right).split()
    if first == second:
        return bool(first)
    if not first or not second or first[-1] != second[-1]:
        return False
    if min(len(first), len(second)) == 1:
        return allow_surname
    if not _same_or_initial(first[0], second[0]):
        return False
    # Missing middle names are compatible in this context; contradictory supplied
    # middle names are not. This function alone never merges global identities.
    return all(
        _same_or_initial(a, b) for a, b in zip(first[1:-1], second[1:-1], strict=False)
    )


def _same_or_initial(left: str, right: str) -> bool:
    return (
        left == right
        or (len(left) == 1 and right.startswith(left))
        or (len(right) == 1 and left.startswith(right))
    )
