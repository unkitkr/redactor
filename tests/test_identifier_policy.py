"""Compose real CSV streaming with scoped, restart-stable identifier policies."""

import csv
from pathlib import Path

import pytest

from redactor.formats.csv import (
    encode_csv_header,
    encode_csv_record,
    inspect_csv,
    iter_csv_records,
)
from redactor.policy.identifiers import replace_identifier, replace_lot, replace_npi
from redactor.policy.keys import evidence_key
from redactor.policy.normalization import normalize_name
from redactor.utils.constants import DEFAULT_RECORD_BYTES
from redactor.utils.errors import ERROR_IDENTIFIER, ERROR_MAPPING_KEY


def test_identifier_policy_replays_across_files_and_preserves_clinical_fields(
    tmp_path: Path,
) -> None:
    source = tmp_path / "input.csv"
    output = tmp_path / "output.csv"
    key = bytes(range(32))
    with source.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(("mrn", "attending_npi", "lot_no", "dx_code", "lab_value"))
        for number in range(1000):
            writer.writerow(
                (f"00{number:05d}", "1234567893", "BATCH-42", "E11.9", "5.6")
            )
    layout = inspect_csv(source, DEFAULT_RECORD_BYTES)
    with output.open("wb") as stream:
        stream.write(encode_csv_header(layout))
        for row in iter_csv_records(source, layout, DEFAULT_RECORD_BYTES):
            mrn, npi, lot, code, lab = row.values
            values = (
                replace_identifier(mrn, key, namespace="mrn"),
                replace_npi(npi, key),
                replace_lot(lot, key),
                code,
                lab,
            )
            stream.write(encode_csv_record(values, layout))

    with output.open(encoding="utf-8-sig", newline="") as stream:
        records = list(csv.DictReader(stream))
    assert len(records) == 1000
    assert len({record["mrn"] for record in records}) == 1000
    for record in records:
        assert record["dx_code"] == "E11.9" and record["lab_value"] == "5.6"
        assert record["mrn"].isdigit() and len(record["mrn"]) == 18
        npi = record["attending_npi"]
        assert len(npi) == 10 and npi[0] in "12" and npi != "1234567893"
        # Independently validate the full ISO-prefixed NPI, including check digit.
        digits = [int(character) for character in reversed("80840" + npi)]
        checksum = sum(
            digit if position % 2 == 0 else (digit * 2 // 10 + digit * 2 % 10)
            for position, digit in enumerate(digits)
        )
        assert checksum % 10 == 0
    assert replace_npi("123-456-7893", key) == records[0]["attending_npi"]
    assert replace_identifier("0000000", key, namespace="mrn") == records[0]["mrn"]
    assert replace_identifier("0000000", key, namespace="account") != records[0]["mrn"]
    assert (
        replace_identifier("0000000", key, namespace="mrn", scope="other")
        != records[0]["mrn"]
    )
    assert (
        replace_identifier("0000000", key[::-1], namespace="mrn") != records[0]["mrn"]
    )
    assert normalize_name("Dr. Jane A. Surname") == normalize_name("Surname, Jane A.")
    assert normalize_name("Surname^Jane^A^Dr.^Jr") != normalize_name(
        "Surname^Jane^A^Dr.^Sr"
    )
    assert normalize_name("J. Surname") != normalize_name("Jane Surname")
    assert evidence_key(key, "Jane Surname", namespace="patient") != evidence_key(
        key, "Jane Surname", namespace="provider"
    )
    with pytest.raises(ValueError, match=ERROR_MAPPING_KEY):
        replace_npi("1234567893", b"short")
    with pytest.raises(ValueError, match=ERROR_IDENTIFIER):
        replace_npi("NPI missing", key)
