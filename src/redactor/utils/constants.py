"""Shared constants; runtime state belongs to callers, not this module."""

from typing import Final, Literal

TaskStatus = Literal["pending", "running", "succeeded", "failed"]
AttemptStatus = Literal["running", "succeeded", "failed", "interrupted"]

STATUS_PENDING: Final = "pending"
STATUS_RUNNING: Final = "running"
STATUS_SUCCEEDED: Final = "succeeded"
STATUS_FAILED: Final = "failed"
STATUS_INTERRUPTED: Final = "interrupted"

STATE_DIRECTORY: Final = ".redactor"
DATABASE_FILENAME: Final = "state.sqlite3"
OUTPUT_DIRECTORY: Final = "output"
PUBLISHED_DIRECTORY: Final = "published"
TEMPORARY_DIRECTORY: Final = "tmp"
TEMPORARY_FILE_TEMPLATE: Final = "{attempt_token}.part"
FILE_LOCATION_FIELDS: Final = ("temporary_directory", "output_path")

INITIAL_SCHEMA_VERSION: Final = 1
SCHEMA_VERSION: Final = 2
SQLITE_TIMEOUT_SECONDS: Final = 5.0
SQLITE_CACHE_KIB: Final = 8192
SQLITE_JOURNAL_MODE: Final = "wal"
SQLITE_SYNCHRONOUS: Final = "FULL"
SQLITE_TEMP_STORE: Final = "FILE"
TRANSACTION_BEGIN: Final = "BEGIN IMMEDIATE"
TRANSACTION_COMMIT: Final = "COMMIT"
TRANSACTION_ROLLBACK: Final = "ROLLBACK"

HASH_CHUNK_BYTES: Final = 1024 * 1024
PRIVATE_DIRECTORY_MODE: Final = 0o700
PRIVATE_FILE_MODE: Final = 0o600
TEXT_ENCODING: Final = "utf-8"
READ_BINARY: Final = "rb"

ERROR_UNSUPPORTED_SCHEMA: Final = "unsupported_state_schema"
ERROR_WAL_UNAVAILABLE: Final = "sqlite_wal_unavailable"
ERROR_NESTED_TRANSACTION: Final = "nested_transaction_not_supported"
ERROR_TASK_NOT_FOUND: Final = "task_not_found"
ERROR_STALE_ATTEMPT: Final = "stale_task_attempt"
ERROR_INVALID_TRANSITION: Final = "invalid_task_transition"
ERROR_UNKNOWN_DEPENDENCY: Final = "unknown_task_dependency"
ERROR_DEPENDENCIES_CHANGED: Final = "task_dependencies_changed"
ERROR_TASK_ID_CONFLICT: Final = "task_identity_conflict"
ERROR_COMPLETION_CHANGED: Final = "accepted_result_changed"
ERROR_INTERRUPTED: Final = "execution_interrupted"
ERROR_INVALID_FAILURE_CODE: Final = "invalid_failure_code"
ERROR_INPUT_CHANGED: Final = "input_fingerprint_changed"
ERROR_FILE_NOT_REGISTERED: Final = "file_not_registered"
ERROR_OUTPUT_CONFLICT: Final = "output_content_conflict"
ERROR_OUTPUT_FILESYSTEM: Final = "output_requires_same_filesystem"
ERROR_INVALID_CHECKPOINT: Final = "invalid_checkpoint_progress"
ERROR_ARTIFACT_MISSING: Final = "checkpoint_artifact_missing"
ERROR_ARTIFACT_CORRUPT: Final = "checkpoint_artifact_corrupt"
ERROR_INCOMPLETE_INPUT: Final = "input_not_fully_consumed"
ERROR_PROCESSING: Final = "processing_error"
ERROR_TIMEOUT: Final = "processing_timeout"

FAILURE_CODES: Final = (
    ERROR_PROCESSING,
    ERROR_TIMEOUT,
    ERROR_INPUT_CHANGED,
    ERROR_ARTIFACT_MISSING,
    ERROR_ARTIFACT_CORRUPT,
    ERROR_INVALID_CHECKPOINT,
    ERROR_INCOMPLETE_INPUT,
)
JSON_SEPARATORS: Final = (",", ":")
