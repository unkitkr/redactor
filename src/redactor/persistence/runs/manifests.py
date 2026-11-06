"""Persist bounded run manifests before registering their dependent tasks."""

import hashlib
import os
import sqlite3

from redactor.persistence.database import state_directory
from redactor.persistence.files.artifacts import inspect_artifact, install_artifact
from redactor.schemas.inventory import RunManifest
from redactor.schemas.persistence import Artifact
from redactor.utils.constants import (
    MAX_MANIFEST_BYTES,
    PRIVATE_FILE_MODE,
    RUN_MANIFEST_FILENAME,
    RUN_MANIFEST_PENDING_FILENAME,
    RUNS_DIRECTORY,
    TEXT_ENCODING,
)
from redactor.utils.errors import ERROR_INVENTORY_LIMIT, ERROR_RUN_CONTEXT
from redactor.utils.filesystem import private_directory, sync_directory


def persist_manifest(connection: sqlite3.Connection, manifest: RunManifest) -> Artifact:
    """The coordinator must hold exclusive run ownership while freezing inventory."""
    payload = manifest.model_dump_json().encode(TEXT_ENCODING)
    if len(payload) > MAX_MANIFEST_BYTES:
        raise ValueError(ERROR_INVENTORY_LIMIT)
    digest = hashlib.sha256(payload).hexdigest()
    directory = state_directory(connection) / RUNS_DIRECTORY / digest
    private_directory(directory)
    temporary_path = directory / RUN_MANIFEST_PENDING_FILENAME
    descriptor = os.open(
        temporary_path,
        os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW,
        PRIVATE_FILE_MODE,
    )
    with os.fdopen(descriptor, "wb") as stream:
        os.fchmod(stream.fileno(), PRIVATE_FILE_MODE)
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())
    sync_directory(directory)
    staged = Artifact(path=temporary_path, sha256=digest, size=len(payload))
    installed = install_artifact(staged, directory / RUN_MANIFEST_FILENAME)
    temporary_path.unlink()
    sync_directory(directory)
    return installed


def read_manifest(artifact: Artifact, expected_key_fingerprint: str) -> RunManifest:
    if artifact.size > MAX_MANIFEST_BYTES:
        raise ValueError(ERROR_RUN_CONTEXT)
    if inspect_artifact(artifact.path, persist=False) != artifact:
        raise ValueError(ERROR_RUN_CONTEXT)
    with artifact.path.open("rb") as stream:
        payload = stream.read(MAX_MANIFEST_BYTES + 1)
    if (
        len(payload) != artifact.size
        or hashlib.sha256(payload).hexdigest() != artifact.sha256
    ):
        raise ValueError(ERROR_RUN_CONTEXT)
    try:
        manifest = RunManifest.model_validate_json(payload)
    except ValueError:
        raise ValueError(ERROR_RUN_CONTEXT) from None
    if manifest.key_fingerprint != expected_key_fingerprint:
        raise ValueError(ERROR_RUN_CONTEXT)
    return manifest
