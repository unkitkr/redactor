"""Immutable inputs and processing policy shared by every worker in a run."""

from pathlib import Path

from pydantic import BaseModel, Field, NonNegativeInt

from redactor.schemas.configuration import PipelineSettings
from redactor.schemas.persistence import Artifact
from redactor.utils.constants import PIPELINE_VERSION, SHA256_PATTERN


class InventoryFile(BaseModel, frozen=True, extra="forbid"):
    input_path: Path
    relative_path: Path
    sha256: str = Field(pattern=SHA256_PATTERN)
    size: NonNegativeInt


class RunManifest(BaseModel, frozen=True, extra="forbid"):
    input_directory: Path
    files: tuple[InventoryFile, ...]
    settings: PipelineSettings
    key_fingerprint: str = Field(pattern=SHA256_PATTERN)
    runtime_fingerprint: str = Field(pattern=SHA256_PATTERN)
    pipeline_version: str = PIPELINE_VERSION


class PreparedRun(BaseModel, frozen=True, extra="forbid"):
    manifest: Artifact
    resolution_task_id: str
