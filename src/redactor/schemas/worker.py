"""Worker startup arguments and the safe subset of task metadata to print."""

from pathlib import Path

from pydantic import BaseModel, ConfigDict, NonNegativeInt, PositiveInt


class WorkerConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    state_directory: Path
    coordinator_pid: PositiveInt
    lock_descriptor: NonNegativeInt


class TaskSummary(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    task_id: str
    step: str
    attempt_count: PositiveInt
    worker_pid: PositiveInt
