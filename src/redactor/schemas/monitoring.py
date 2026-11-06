"""Bounded queue metadata with no paths, identifying payloads, or worker claims."""

from pydantic import AwareDatetime, BaseModel, Field, NonNegativeInt

from redactor.utils.constants import (
    MONITOR_MAX_RUNS,
    MONITOR_MAX_TASKS,
    MONITOR_RUN_ID_PATTERN,
    SHA256_PATTERN,
    MonitorStatus,
    MonitorStep,
    TaskStatus,
)


class RunSummary(BaseModel, frozen=True, extra="forbid"):
    processing_version: str = Field(pattern=MONITOR_RUN_ID_PATTERN)
    created_at: AwareDatetime
    updated_at: AwareDatetime
    task_count: NonNegativeInt


class StepCounts(BaseModel, frozen=True, extra="forbid"):
    step: MonitorStep
    pending: NonNegativeInt = 0
    running: NonNegativeInt = 0
    succeeded: NonNegativeInt = 0
    failed: NonNegativeInt = 0
    total: NonNegativeInt = 0


class TaskProgress(BaseModel, frozen=True, extra="forbid"):
    task_id: str = Field(pattern=SHA256_PATTERN)
    step: MonitorStep
    status: TaskStatus
    attempt_count: NonNegativeInt
    updated_at: AwareDatetime
    failure_code: str | None = None
    checkpoint_records: NonNegativeInt | None = None
    input_offset: NonNegativeInt | None = None


class QueueSnapshot(BaseModel, frozen=True, extra="forbid"):
    """Committed task state only: running does not mean a worker is still alive."""

    status: MonitorStatus
    reason_code: str | None = None
    observed_at: AwareDatetime
    processing_version: str | None = Field(default=None, pattern=MONITOR_RUN_ID_PATTERN)
    runs: tuple[RunSummary, ...] = Field(default=(), max_length=MONITOR_MAX_RUNS)
    steps: tuple[StepCounts, ...] = ()
    tasks: tuple[TaskProgress, ...] = Field(default=(), max_length=MONITOR_MAX_TASKS)
    task_count: NonNegativeInt = 0
    published_files: NonNegativeInt = 0
    quarantined_files: NonNegativeInt = 0
    resolve_tasks: NonNegativeInt = 0
