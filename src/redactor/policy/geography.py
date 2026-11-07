"""Apply the assignment's ZIP3 generalization without confusing codes with ZIPs."""

import re

from redactor.utils.constants import (
    RESTRICTED_ZIP_PREFIXES,
    ZIP_CODE_PATTERN,
    ZIP_REDACTED_PREFIX,
)
from redactor.utils.errors import ERROR_IDENTIFIER

_ZIP_CODE = re.compile(ZIP_CODE_PATTERN)


def generalize_zip(value: str) -> str:
    """Call only for a location already identified as a ZIP field or text span."""
    if _ZIP_CODE.fullmatch(value) is None:
        raise ValueError(ERROR_IDENTIFIER)
    prefix = value[:3]
    return ZIP_REDACTED_PREFIX if prefix in RESTRICTED_ZIP_PREFIXES else prefix
