"""UTF-8 CSV/TSV with explicit complete-record byte offsets, including quoted lines."""

import csv
import io
from collections.abc import Callable, Generator, Iterator, Sequence
from pathlib import Path
from typing import BinaryIO, Literal

from redactor.schemas.tabular import CsvLayout, CsvRecord
from redactor.utils.constants import (
    CSV_DELIMITERS,
    CSV_SNIFF_BYTES,
    LINE_ENDING_CRLF,
    LINE_ENDING_LF,
    TEXT_ENCODING,
    UTF8_BOM,
)
from redactor.utils.errors import (
    ERROR_CSV_RECORD_LIMIT,
    ERROR_CSV_STRUCTURE,
    ERROR_TEXT_ENCODING,
)


def inspect_csv(path: Path, maximum_record_bytes: int) -> CsvLayout:
    """Recognize a delimited header; the analysis pass validates every data record."""
    with path.open("rb") as stream:
        sample = stream.read(min(CSV_SNIFF_BYTES, maximum_record_bytes))
        has_bom = sample.startswith(UTF8_BOM)
        if has_bom:
            sample = sample[len(UTF8_BOM) :]
        # A bounded sample can end inside a code point or quoted record. Use its
        # complete physical lines only for delimiter sniffing, never as records.
        line_boundary = sample.rfind(b"\n")
        if line_boundary >= 0:
            sample = sample[: line_boundary + 1]
        try:
            text = sample.decode(TEXT_ENCODING)
            dialect = csv.Sniffer().sniff(text, delimiters="".join(CSV_DELIMITERS))
        except UnicodeDecodeError:
            raise ValueError(ERROR_TEXT_ENCODING) from None
        except csv.Error:
            raise ValueError(ERROR_CSV_STRUCTURE) from None
        delimiter = dialect.delimiter
        if delimiter not in CSV_DELIMITERS or dialect.quotechar != '"':
            raise ValueError(ERROR_CSV_STRUCTURE)
        stream.seek(len(UTF8_BOM) if has_bom else 0)
        records = _read_records(stream, delimiter, maximum_record_bytes)
        header = next(records, None)
        if header is None or len(header[0]) < 2 or not all(header[0]):
            raise ValueError(ERROR_CSV_STRUCTURE)
        if len(set(header[0])) != len(header[0]):
            raise ValueError(ERROR_CSV_STRUCTURE)
        ending: Literal["\n", "\r\n"] = (
            LINE_ENDING_CRLF if b"\r\n" in sample else LINE_ENDING_LF
        )
        return CsvLayout(
            delimiter=delimiter,
            line_ending=ending,
            has_bom=has_bom,
            columns=header[0],
            header_end_offset=header[1],
        )


def iter_csv_records(
    path: Path,
    layout: CsvLayout,
    maximum_record_bytes: int,
    *,
    start_offset: int | None = None,
    completed_records: int = 0,
) -> Generator[CsvRecord, None, None]:
    """Offsets supplied on resume must come from a previously committed record."""
    offset = layout.header_end_offset if start_offset is None else start_offset
    if offset < layout.header_end_offset or completed_records < 0:
        raise ValueError(ERROR_CSV_STRUCTURE)
    with path.open("rb") as stream:
        if offset > path.stat().st_size:
            raise ValueError(ERROR_CSV_STRUCTURE)
        stream.seek(offset)
        for number, (values, end_offset) in enumerate(
            _read_records(stream, layout.delimiter, maximum_record_bytes),
            start=completed_records + 1,
        ):
            if len(values) != len(layout.columns):
                raise ValueError(ERROR_CSV_STRUCTURE)
            yield CsvRecord(number=number, values=values, end_offset=end_offset)


def encode_csv_record(values: Sequence[str], layout: CsvLayout) -> bytes:
    with io.StringIO(newline="") as text:
        writer = csv.writer(
            text, delimiter=layout.delimiter, lineterminator=layout.line_ending
        )
        writer.writerow(values)
        return text.getvalue().encode(TEXT_ENCODING)


def csv_record_encoder(layout: CsvLayout) -> Callable[[Sequence[str]], bytes]:
    """Reuse the CSV writer and its bounded record buffer within one file."""
    text = io.StringIO(newline="")
    writer = csv.writer(
        text, delimiter=layout.delimiter, lineterminator=layout.line_ending
    )

    def encode(values: Sequence[str]) -> bytes:
        text.seek(0)
        text.truncate()
        writer.writerow(values)
        return text.getvalue().encode(TEXT_ENCODING)

    return encode


def encode_csv_header(layout: CsvLayout) -> bytes:
    bom = UTF8_BOM if layout.has_bom else b""
    return bom + encode_csv_record(layout.columns, layout)


def _read_records(
    stream: BinaryIO, delimiter: str, maximum_record_bytes: int
) -> Generator[tuple[tuple[str, ...], int], None, None]:
    # csv exposes a process-wide character limit, not a per-reader option. Only
    # raise it so interleaved readers cannot invalidate each other. The byte bound
    # below remains authoritative for each reader, including quoted multiline data.
    csv.field_size_limit(max(csv.field_size_limit(), maximum_record_bytes))
    record_start_offset = stream.tell()

    def physical_lines() -> Iterator[str]:
        while line := stream.readline(maximum_record_bytes + 1):
            if stream.tell() - record_start_offset > maximum_record_bytes:
                raise ValueError(ERROR_CSV_RECORD_LIMIT)
            try:
                yield line.decode(TEXT_ENCODING)
            except UnicodeDecodeError:
                raise ValueError(ERROR_TEXT_ENCODING) from None

    reader = csv.reader(physical_lines(), delimiter=delimiter, strict=True)
    try:
        for values in reader:
            yield tuple(values), stream.tell()
            record_start_offset = stream.tell()
    except csv.Error:
        raise ValueError(ERROR_CSV_STRUCTURE) from None
