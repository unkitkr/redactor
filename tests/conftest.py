import sqlite3
from collections.abc import Iterator
from contextlib import closing
from pathlib import Path

import pytest

from redactor.persistence.database import open_database
from redactor.utils.constants import STATE_DIRECTORY


@pytest.fixture
def source_file(tmp_path: Path) -> Path:
    source = tmp_path / "records.txt"
    source.write_bytes(b"one\ntwo\nthree\n")
    return source


@pytest.fixture
def connection(tmp_path: Path) -> Iterator[sqlite3.Connection]:
    with closing(open_database(tmp_path / STATE_DIRECTORY)) as database:
        yield database
