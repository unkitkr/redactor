"""Validated startup configuration; paths are resolved by the entry point."""

from pathlib import Path

from pydantic import BaseModel, ConfigDict, PositiveInt

from redactor.utils.constants import DEFAULT_WORKER_COUNT


class CoordinatorConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    input_directory: Path
    state_directory: Path
    worker_count: PositiveInt = DEFAULT_WORKER_COUNT
