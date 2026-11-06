"""Distinguish a temporarily idle queue from completion or blocked dependencies."""

import json
import sqlite3
from collections.abc import Collection

from redactor.utils.constants import STATUS_PENDING, STATUS_RUNNING, STATUS_SUCCEEDED
from redactor.utils.errors import ERROR_PIPELINE_BLOCKED


def work_remains(
    connection: sqlite3.Connection,
    processing_version: str,
    steps: Collection[str],
) -> bool:
    """Read one consistent snapshot so completion cannot race a liveness check."""
    row = connection.execute(
        """
        SELECT
            count(*) FILTER (WHERE status = ?) AS running,
            count(*) FILTER (WHERE status = ?) AS pending,
            count(*) FILTER (WHERE status = ? AND NOT EXISTS (
                SELECT 1 FROM dependencies
                JOIN tasks AS parent ON parent.task_id = depends_on
                WHERE dependencies.task_id = tasks.task_id AND parent.status != ?
            )) AS ready
        FROM tasks
        WHERE processing_version = ? AND step IN (SELECT value FROM json_each(?))
        """,
        (
            STATUS_RUNNING,
            STATUS_PENDING,
            STATUS_PENDING,
            STATUS_SUCCEEDED,
            processing_version,
            json.dumps(sorted(steps)),
        ),
    ).fetchone()
    if row["pending"] and not row["running"] and not row["ready"]:
        raise RuntimeError(ERROR_PIPELINE_BLOCKED)
    return bool(row["running"] or row["pending"])
