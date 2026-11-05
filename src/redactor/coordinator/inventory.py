"""Discover regular input files without materializing the inventory in memory."""

import os
import sqlite3
from collections.abc import Iterator
from pathlib import Path

from redactor.persistence.files import register_file
from redactor.utils.constants import (
    BOOTSTRAP_PROCESSING_VERSION,
    OUTPUT_DIRECTORY,
    PRINT_TASK_STEP,
)
from redactor.utils.errors import (
    ERROR_DIRECTORY_OVERLAP,
    ERROR_INPUT_DIRECTORY,
    ERROR_INPUT_ENTRY,
)


def validate_directories(input_directory: Path, state_directory: Path) -> None:
    """Reject invalid input and overlap before creating any runtime files."""
    input_directory = input_directory.resolve()
    state_directory = state_directory.resolve()
    if not input_directory.is_dir():
        raise ValueError(ERROR_INPUT_DIRECTORY)

    output_directory = (state_directory.parent / OUTPUT_DIRECTORY).resolve()
    for runtime_directory in (state_directory, output_directory):
        if input_directory.is_relative_to(runtime_directory) or (
            runtime_directory.is_relative_to(input_directory)
        ):
            raise ValueError(ERROR_DIRECTORY_OVERLAP)


def iter_input_files(directory: Path) -> Iterator[Path]:
    """Walk without following symlinks or trusting filename extensions."""
    with os.scandir(directory) as entries:
        for entry in entries:
            if entry.is_dir(follow_symlinks=False):
                yield from iter_input_files(Path(entry.path))
            elif entry.is_file(follow_symlinks=False):
                yield Path(entry.path)
            else:
                raise ValueError(ERROR_INPUT_ENTRY)


def register_inputs(connection: sqlite3.Connection, input_directory: Path) -> None:
    """Commit each file separately; interrupted discovery is safe to repeat."""
    for input_path in iter_input_files(input_directory):
        register_file(
            connection, input_path, PRINT_TASK_STEP, BOOTSTRAP_PROCESSING_VERSION
        )
