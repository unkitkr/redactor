"""Require saved workbooks to load through an independent standard parser."""

import warnings
from pathlib import Path

from openpyxl import load_workbook

from redactor.utils.errors import ERROR_STRUCTURE


def check_workbook_tooling(path: Path) -> None:
    # Native surface checks already inspect every cell and XML carrier. Read-only
    # loading separately validates workbook relationships and style references
    # without allocating a second object for every worksheet cell.
    try:
        with path.open("rb") as stream, warnings.catch_warnings():
            warnings.simplefilter("error")
            # Use detected content rather than the staged or mislabeled suffix.
            workbook = load_workbook(stream, read_only=True, keep_links=False)
            try:
                if not workbook.worksheets:
                    raise ValueError(ERROR_STRUCTURE)
            finally:
                workbook.close()
    except Exception:
        # Parser messages and warnings can contain identifying labels.
        raise ValueError(ERROR_STRUCTURE) from None
