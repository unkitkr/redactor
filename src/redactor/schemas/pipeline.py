"""Functional step contracts; no runtime dependencies are stored in the queue."""

import sqlite3
from collections.abc import Callable

from pydantic import BaseModel

from redactor.schemas.persistence import Artifact, Task, TaskSpec


class StepResult(BaseModel, frozen=True, extra="forbid"):
    artifact: Artifact | None = None
    successors: tuple[TaskSpec, ...] = ()


StepHandler = Callable[[sqlite3.Connection, Task], StepResult]
