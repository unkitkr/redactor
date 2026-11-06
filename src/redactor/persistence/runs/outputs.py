"""Bind an output directory to one frozen run before workers can publish into it."""

import sqlite3

from redactor.persistence.database import state_directory
from redactor.persistence.files.artifacts import inspect_artifact, install_artifact
from redactor.persistence.files.reports import replace_report
from redactor.schemas.persistence import Artifact
from redactor.utils.constants import (
    OUTPUT_DIRECTORY,
    OUTPUT_OWNER_FILENAME,
    TEXT_ENCODING,
)
from redactor.utils.errors import ERROR_OUTPUT_CONFLICT
from redactor.utils.filesystem import private_directory


def bind_output_directory(connection: sqlite3.Connection, manifest: Artifact) -> None:
    """A policy upgrade cannot leave older publications beside a newer clean report."""
    output = state_directory(connection).parent / OUTPUT_DIRECTORY
    private_directory(output)
    owner = output / OUTPUT_OWNER_FILENAME
    if not owner.exists() and any(output.iterdir()):
        # Existing unowned outputs might have passed an older verification policy.
        # Preserve them and require a fresh workspace instead of relabelling them.
        raise ValueError(ERROR_OUTPUT_CONFLICT)
    receipt = manifest.path.with_name(OUTPUT_OWNER_FILENAME)
    replace_report(receipt, (manifest.sha256 + "\n").encode(TEXT_ENCODING))
    install_artifact(inspect_artifact(receipt, persist=True), owner)
