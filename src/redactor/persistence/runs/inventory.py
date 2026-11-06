"""Derive file work from a frozen run without rereading large source files."""

import sqlite3

from redactor.persistence.database import state_directory
from redactor.persistence.files.registration import prepare_successor
from redactor.schemas.inventory import InventoryFile
from redactor.schemas.persistence import Artifact, TaskSpec
from redactor.utils.constants import OUTPUT_DIRECTORY, PUBLISHED_DIRECTORY


def file_step(
    connection: sqlite3.Connection,
    manifest: Artifact,
    source: InventoryFile,
    step: str,
) -> TaskSpec:
    output_directory = state_directory(connection).parent / OUTPUT_DIRECTORY
    source_spec = TaskSpec(
        task_id=source.sha256,
        input_path=source.input_path,
        input_sha256=source.sha256,
        input_size=source.size,
        step=step,
        processing_version=manifest.sha256,
        output_path=output_directory / PUBLISHED_DIRECTORY / source.relative_path,
    )
    return prepare_successor(connection, source_spec, step)
