"""Reparse serialized CSV independently of the rewrite adapter's cursors."""

import csv
from collections.abc import Generator
from pathlib import Path

from redactor.utils.constants import TEXT_ENCODING, UTF8_BOM
from redactor.utils.errors import ERROR_CSV_RECORD_LIMIT, ERROR_STRUCTURE


def read_csv_rows(
    path: Path, delimiter: str, maximum_record_bytes: int
) -> Generator[tuple[str, ...], None, None]:
    csv.field_size_limit(max(csv.field_size_limit(), maximum_record_bytes))
    with path.open("rb") as stream:
        if stream.read(len(UTF8_BOM)) != UTF8_BOM:
            stream.seek(0)
        record_bytes = 0

        def lines() -> Generator[str, None, None]:
            nonlocal record_bytes
            while payload := stream.readline(maximum_record_bytes + 1):
                record_bytes += len(payload)
                if record_bytes > maximum_record_bytes:
                    raise ValueError(ERROR_CSV_RECORD_LIMIT)
                yield payload.decode(TEXT_ENCODING)

        try:
            for row in csv.reader(lines(), delimiter=delimiter, strict=True):
                yield tuple(row)
                record_bytes = 0
        except (csv.Error, UnicodeError):
            raise ValueError(ERROR_STRUCTURE) from None
