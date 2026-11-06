"""Validated startup configuration; paths are resolved by the entry point."""

from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, PositiveInt

from redactor.utils.constants import (
    DEFAULT_WORKER_COUNT,
    MONITOR_DEFAULT_ENABLED,
    MONITOR_MAX_PORT,
    MONITOR_PORT,
)


class CoordinatorConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    input_directory: Path
    state_directory: Path
    worker_count: PositiveInt = DEFAULT_WORKER_COUNT
    configuration_path: Path | None = None
    diagnostic: bool = False
    dashboard_enabled: bool = MONITOR_DEFAULT_ENABLED
    dashboard_port: int = Field(default=MONITOR_PORT, ge=1, le=MONITOR_MAX_PORT)
