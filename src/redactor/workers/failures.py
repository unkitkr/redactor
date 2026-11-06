"""Keep actionable diagnostics without exception messages, paths or input data."""

import os
import sqlite3
import sys
from pathlib import Path

from redactor.persistence.files.reports import replace_report
from redactor.schemas.diagnostics import FailureDiagnostic
from redactor.utils.constants import (
    FAILURE_FILESYSTEM,
    FAILURE_MEMORY,
    FAILURE_SQLITE,
    FAILURE_UNEXPECTED,
    FAILURE_VALIDATION,
    WORKER_FAILURE_FILENAME,
)
from redactor.utils.failures import failure_reason


def record_worker_failure(directory: Path, error: Exception) -> None:
    diagnostic = describe_failure(error)
    payload = diagnostic.model_dump_json()
    print(payload, file=sys.stderr, flush=True)
    try:
        replace_report(
            directory / WORKER_FAILURE_FILENAME.format(pid=os.getpid()),
            payload.encode(),
        )
    except (OSError, ValueError):
        # Disk failure must not hide the original diagnostic from the supervisor.
        pass


def describe_failure(error: Exception) -> FailureDiagnostic:
    reason = failure_reason(error)
    if isinstance(error, sqlite3.Error):
        return FailureDiagnostic(
            reason=reason,
            category=FAILURE_SQLITE,
            sqlite_error_code=getattr(error, "sqlite_errorcode", None),
        )
    if isinstance(error, OSError):
        return FailureDiagnostic(
            reason=reason, category=FAILURE_FILESYSTEM, os_error_code=error.errno
        )
    if isinstance(error, MemoryError):
        return FailureDiagnostic(reason=reason, category=FAILURE_MEMORY)
    return FailureDiagnostic(
        reason=reason,
        category=FAILURE_VALIDATION
        if isinstance(error, ValueError)
        else FAILURE_UNEXPECTED,
    )
