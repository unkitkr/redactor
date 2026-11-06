"""Only exact known field labels are structural; unknown labels need PHI checks."""

import re

from redactor.schemas.entities import NerAdapter
from redactor.utils.constants import TABULAR_FIELD_ALIASES
from redactor.verification.text import verify_text_changes


def verify_column_headers(columns: tuple[str, ...], local_ner: NerAdapter) -> None:
    known = {alias for _, _, aliases in TABULAR_FIELD_ALIASES for alias in aliases}
    for column in columns:
        normalized = re.sub(r"[\s-]+", "_", column.strip().casefold())
        if normalized not in known:
            verify_text_changes(column, column, (), local_ner, free_text=True)
