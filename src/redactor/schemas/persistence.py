"""Structured records exchanged by the queue and durability functions."""

from pathlib import Path

from pydantic import BaseModel, Field, JsonValue, NonNegativeInt, PositiveInt

from redactor.utils.constants import AttemptStatus, TaskStatus


class TaskSpec(BaseModel, frozen=True, extra="forbid"):
    """A stable input and operation identity, prepared before a transaction."""

    task_id: str
    input_path: Path
    input_sha256: str
    input_size: NonNegativeInt
    step: str = Field(min_length=1)
    processing_version: str = Field(min_length=1)
    temporary_directory: Path | None = None
    output_path: Path | None = None


class Task(TaskSpec, frozen=True):
    status: TaskStatus
    attempt_token: str | None
    attempt_count: NonNegativeInt
    failure_code: str | None
    created_at: str
    updated_at: str
    result_path: Path | None
    result_sha256: str | None
    result_size: NonNegativeInt | None


class Attempt(BaseModel, frozen=True, extra="forbid"):
    task_id: str
    attempt_token: str
    status: AttemptStatus
    started_at: str
    finished_at: str | None
    failure_code: str | None


class Checkpoint(BaseModel, frozen=True, extra="forbid"):
    """Byte positions must be complete-record boundaries supplied by an adapter."""

    sequence: PositiveInt
    task_id: str
    artifact_path: Path
    input_offset: NonNegativeInt
    output_offset: NonNegativeInt
    record_count: NonNegativeInt
    output_prefix_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    counts: dict[str, NonNegativeInt] = Field(default_factory=dict)
    adapter_version: str = Field(min_length=1)
    cursor: dict[str, JsonValue] = Field(default_factory=dict)


class Artifact(BaseModel, frozen=True, extra="forbid"):
    """A durable staged result, not a declaration that its content is PHI-free."""

    path: Path
    sha256: str
    size: NonNegativeInt
