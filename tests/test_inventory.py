import sqlite3
from pathlib import Path

import pytest

from redactor.coordinator.inventory import (
    iter_input_files,
    register_inputs,
    validate_directories,
)
from redactor.persistence.queue import iter_tasks
from redactor.utils.constants import (
    BOOTSTRAP_PROCESSING_VERSION,
    OUTPUT_DIRECTORY,
    PRINT_TASK_STEP,
    STATE_DIRECTORY,
)
from redactor.utils.errors import (
    ERROR_DIRECTORY_OVERLAP,
    ERROR_INPUT_DIRECTORY,
    ERROR_INPUT_ENTRY,
)


def test_nested_inventory_is_streamed_and_registration_is_repeatable(
    connection: sqlite3.Connection, tmp_path: Path
) -> None:
    inputs = tmp_path / "input"
    nested = inputs / "nested"
    nested.mkdir(parents=True)
    files = [inputs / "no_extension", nested / "misleading.csv"]
    for path in files:
        path.write_bytes(b"not actually csv")

    assert set(iter_input_files(inputs)) == set(files)
    register_inputs(connection, inputs)
    original = list(iter_tasks(connection))
    register_inputs(connection, inputs)
    assert list(iter_tasks(connection)) == original
    assert {task.input_path for task in original} == set(files)
    assert all(task.step == PRINT_TASK_STEP for task in original)
    assert all(
        task.processing_version == BOOTSTRAP_PROCESSING_VERSION for task in original
    )


def test_inventory_rejects_symlinks(tmp_path: Path, source_file: Path) -> None:
    inputs = tmp_path / "input"
    inputs.mkdir()
    (inputs / "alias").symlink_to(source_file)
    with pytest.raises(ValueError, match=ERROR_INPUT_ENTRY):
        list(iter_input_files(inputs))


@pytest.mark.parametrize("input_name", [".", STATE_DIRECTORY, OUTPUT_DIRECTORY])
def test_inventory_cannot_include_runtime_directories(
    tmp_path: Path, input_name: str
) -> None:
    inputs = tmp_path / input_name
    inputs.mkdir(exist_ok=True)
    with pytest.raises(ValueError, match=ERROR_DIRECTORY_OVERLAP):
        validate_directories(inputs, tmp_path / STATE_DIRECTORY)


def test_missing_input_is_rejected_before_creating_state(tmp_path: Path) -> None:
    state_directory = tmp_path / STATE_DIRECTORY
    with pytest.raises(ValueError, match=ERROR_INPUT_DIRECTORY):
        validate_directories(tmp_path / "missing", state_directory)
    assert not state_directory.exists()


def test_sibling_input_and_state_are_valid(tmp_path: Path) -> None:
    inputs = tmp_path / "input"
    inputs.mkdir()
    validate_directories(inputs, tmp_path / STATE_DIRECTORY)
    assert list(iter_input_files(inputs)) == []
