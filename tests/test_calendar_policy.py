"""Calendar and ZIP policies applied together to saved, independently read CSV."""

import csv
from datetime import date, datetime, timedelta
from pathlib import Path

import pytest

from redactor.formats.csv import (
    encode_csv_header,
    encode_csv_record,
    inspect_csv,
    iter_csv_records,
)
from redactor.policy.ages import (
    completed_years,
    generalize_age,
    needs_birth_date_generalization,
    replace_birth_date,
)
from redactor.policy.dates import patient_date_offset, shift_date
from redactor.policy.geography import generalize_zip
from redactor.utils.constants import DEFAULT_RECORD_BYTES
from redactor.utils.errors import ERROR_AGE_REPRESENTATION, ERROR_DATE


def test_saved_dates_preserve_intervals_and_protect_explicit_and_derived_age(
    tmp_path: Path,
) -> None:
    source = tmp_path / "input.csv"
    output = tmp_path / "output.csv"
    source.write_text(
        "birth_date,admit_ts,discharge_ts,zip,dx,cpt,lab\n"
        "1936-11-06,2026-11-06T23:15:00-05:00,2026-11-08T08:00:00-05:00,03601,E11.9,94010,5.6\n"
        "1937-01-01,2026-11-06T23:15:00-05:00,2026-11-08T08:00:00-05:00,02139-1234,E11.9,94010,5.6\n",
        encoding="utf-8",
    )
    layout = inspect_csv(source, DEFAULT_RECORD_BYTES)
    key = bytes(range(32))
    offset = patient_date_offset(key, "patient-identity", 365)
    assert 0 < abs(offset) <= 365
    assert patient_date_offset(key, "patient-identity", 365) == offset
    with output.open("wb") as stream:
        stream.write(encode_csv_header(layout))
        for row in iter_csv_records(source, layout, DEFAULT_RECORD_BYTES):
            birth, admission, discharge, zip_code, diagnosis, procedure, lab = (
                row.values
            )
            reference = datetime.fromisoformat(admission).date()
            older = needs_birth_date_generalization(
                date.fromisoformat(birth), reference, offset
            )
            values = (
                replace_birth_date(
                    birth,
                    offset,
                    older_age_group=older,
                    cohort_reference=reference,
                    supports_bounds=True,
                ),
                shift_date(admission, offset),
                shift_date(discharge, offset),
                generalize_zip(zip_code),
                diagnosis,
                procedure,
                lab,
            )
            stream.write(encode_csv_record(values, layout))

    with output.open(encoding="utf-8", newline="") as stream:
        saved = list(csv.DictReader(stream))
    assert len(saved) == 2
    original_start = datetime.fromisoformat("2026-11-06T23:15:00-05:00")
    original_end = datetime.fromisoformat("2026-11-08T08:00:00-05:00")
    for saved_row in saved:
        start = datetime.fromisoformat(saved_row["admit_ts"])
        end = datetime.fromisoformat(saved_row["discharge_ts"])
        assert start - original_start == timedelta(days=offset)
        assert end - start == original_end - original_start
        assert (saved_row["dx"], saved_row["cpt"], saved_row["lab"]) == (
            "E11.9",
            "94010",
            "5.6",
        )
    assert saved[0]["zip"] == "000" and saved[1]["zip"] == "021"
    assert (
        saved[0]["birth_date"]
        == f"on or before {(original_start + timedelta(days=offset)).year - 90}"
    )
    assert (
        saved[1]["birth_date"]
        == (date(1937, 1, 1) + timedelta(days=offset)).isoformat()
    )
    assert generalize_age(89) == "89"
    assert generalize_age(90) == generalize_age(108) == "90+"
    assert completed_years(date(1936, 11, 6), date(2026, 11, 5)) == 89
    assert completed_years(date(1936, 11, 6), date(2026, 11, 6)) == 90
    # Same-day shifts can change calendar age near a leap-day birthday.
    assert needs_birth_date_generalization(date(1936, 2, 29), date(2026, 2, 28), 1)
    assert shift_date("2024-02-29T12:30:15.120Z", 1) == "2024-03-01T12:30:15.120Z"
    assert shift_date("20240229123000-0500", 1) == "20240301123000-0500"
    assert shift_date("2024022912", 1) == "2024030112"
    assert shift_date("2/29/2024", 1) == "3/01/2024"
    assert shift_date("29-Feb-2024", 1) == "01-Mar-2024"
    assert shift_date("February 29, 2024", 1) == "March 01, 2024"
    assert shift_date("4 JUNE 2026", -5) == "30 MAY 2026"
    for invalid in ("2023-02-29", "2024-02", "2024-02-29T12:30:00+01:99"):
        with pytest.raises(ValueError, match=ERROR_DATE):
            shift_date(invalid, offset)
    with pytest.raises(ValueError, match=ERROR_AGE_REPRESENTATION):
        replace_birth_date(
            "1936-11-06",
            offset,
            older_age_group=True,
            cohort_reference=date(2026, 11, 6),
            supports_bounds=False,
        )
