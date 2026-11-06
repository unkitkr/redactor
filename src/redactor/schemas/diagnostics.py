"""Value-free process diagnostics that remain usable when SQLite is unavailable."""

from typing import Literal

from pydantic import BaseModel, NonNegativeInt


class FailureDiagnostic(BaseModel, frozen=True, extra="forbid"):
    reason: str
    category: Literal["sqlite", "filesystem", "memory", "validation", "unexpected"]
    sqlite_error_code: NonNegativeInt | None = None
    os_error_code: NonNegativeInt | None = None


class WorkerExit(BaseModel, frozen=True, extra="forbid"):
    reason: str
    worker_index: NonNegativeInt
    exit_code: int
