"""Complete CSV records survive a durable restart, including quotes and newlines."""

import csv
import hashlib
import sqlite3
from pathlib import Path

import pytest

from redactor.formats.csv import (
    encode_csv_header,
    encode_csv_record,
    inspect_csv,
    iter_csv_records,
)
from redactor.persistence.files.artifacts import create_temporary_file
from redactor.persistence.files.checkpoints import resume_checkpoint, save_checkpoint
from redactor.persistence.files.registration import register_file
from redactor.persistence.queue.tasks import claim_task, recover_interrupted
from redactor.schemas.persistence import Checkpoint
from redactor.utils.constants import CSV_ADAPTER_VERSION, DEFAULT_RECORD_BYTES
from redactor.utils.errors import ERROR_CSV_RECORD_LIMIT, ERROR_CSV_STRUCTURE


def test_csv_checkpoint_resumes_multiline_records_without_duplicates(
    connection: sqlite3.Connection, tmp_path: Path
) -> None:
    source = tmp_path / "records.csv"
    rows = [
        ["one", 'quoted "value"\nsecond line', "12.5"],
        ["two", "Renée, label", "6.0"],
        ["three", "multiple\r\nphysical\r\nlines", "0"],
        ["four", "a large quoted field, " * 10_000, "1"],
    ]
    with source.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.writer(stream, lineterminator="\r\n")
        writer.writerow(["code", "comment", "value"])
        writer.writerows(rows)
    layout = inspect_csv(source, DEFAULT_RECORD_BYTES)
    assert layout.has_bom
    assert layout.line_ending == "\r\n"
    records = list(iter_csv_records(source, layout, DEFAULT_RECORD_BYTES))
    assert [list(record.values) for record in records] == rows
    assert records[-1].end_offset == source.stat().st_size

    register_file(connection, source, "rewrite", "csv-resume-v1")
    claimed = claim_task(connection)
    assert claimed is not None
    staged = create_temporary_file(connection, claimed)
    prefix = encode_csv_header(layout) + encode_csv_record(records[0].values, layout)
    staged.write_bytes(prefix)
    save_checkpoint(
        connection,
        claimed,
        Checkpoint(
            sequence=1,
            task_id=claimed.task_id,
            artifact_path=staged,
            input_offset=records[0].end_offset,
            output_offset=len(prefix),
            record_count=1,
            output_prefix_sha256=hashlib.sha256(prefix).hexdigest(),
            counts={"records": 1},
            adapter_version=CSV_ADAPTER_VERSION,
            cursor={"record": 1},
        ),
    )
    with staged.open("ab") as stream:
        stream.write(b'"uncommitted partial record')
    recover_interrupted(connection)
    resumed_task = claim_task(connection)
    assert resumed_task is not None
    checkpoint = resume_checkpoint(connection, resumed_task, CSV_ADAPTER_VERSION)
    assert checkpoint is not None
    with checkpoint.artifact_path.open("ab") as stream:
        for record in iter_csv_records(
            source,
            layout,
            DEFAULT_RECORD_BYTES,
            start_offset=checkpoint.input_offset,
            completed_records=checkpoint.record_count,
        ):
            stream.write(encode_csv_record(record.values, layout))
    assert checkpoint.artifact_path.read_bytes() == source.read_bytes()
    with checkpoint.artifact_path.open(encoding="utf-8-sig", newline="") as stream:
        reparsed = list(csv.reader(stream))
    assert reparsed == [list(layout.columns), *rows]


def test_csv_rejects_unfinished_records_column_changes_and_oversized_records(
    tmp_path: Path,
) -> None:
    source = tmp_path / "records.csv"
    source.write_bytes(b"code,value\none,two\n")
    layout = inspect_csv(source, 1024)
    for payload, reason in (
        (b'"unfinished\n', ERROR_CSV_STRUCTURE),
        (b"one,two,three\n", ERROR_CSV_STRUCTURE),
        (b'"' + b"x" * 2048 + b"\n", ERROR_CSV_RECORD_LIMIT),
    ):
        source.write_bytes(encode_csv_header(layout) + payload)
        with pytest.raises(ValueError, match=reason):
            list(iter_csv_records(source, layout, 1024))
