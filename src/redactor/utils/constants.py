"""Project constants grouped by responsibility; runtime state stays with callers."""

from typing import Final, Literal

# Task and attempt states
TaskStatus = Literal["pending", "running", "succeeded", "failed"]
AttemptStatus = Literal["running", "succeeded", "failed", "interrupted"]

STATUS_PENDING: Final = "pending"
STATUS_RUNNING: Final = "running"
STATUS_SUCCEEDED: Final = "succeeded"
STATUS_FAILED: Final = "failed"
STATUS_INTERRUPTED: Final = "interrupted"

# File locations and metadata
INPUT_DIRECTORY: Final = "input"
STATE_DIRECTORY: Final = ".redactor"
DATABASE_FILENAME: Final = "state.sqlite3"
OUTPUT_DIRECTORY: Final = "output"
PUBLISHED_DIRECTORY: Final = "published"
TEMPORARY_DIRECTORY: Final = "tmp"
TEMPORARY_FILE_TEMPLATE: Final = "{attempt_token}.part"
FILE_LOCATION_FIELDS: Final = ("temporary_directory", "output_path")

# Coordinator ownership and placeholder work
RUN_LOCK_FILENAME: Final = "coordinator.lock"
PRINT_TASK_STEP: Final = "print_task"
BOOTSTRAP_PROCESSING_VERSION: Final = "bootstrap-v1"

# Worker processes and exit status
WORKER_MODULE: Final = "redactor.workers"
DEFAULT_WORKER_COUNT: Final = 2
WORKER_POLL_SECONDS: Final = 0.05
WORKER_SHUTDOWN_SECONDS: Final = 2.0
EXIT_SUCCESS: Final = 0
EXIT_FAILURE: Final = 1
SIGNAL_EXIT_BASE: Final = 128

# Migration filenames
SQL_SUFFIX: Final = ".sql"
MIGRATION_FILENAME_PATTERN: Final = r"([0-9]+)_.+\.sql"

# SQLite configuration and transactions
SQLITE_TIMEOUT_SECONDS: Final = 5.0
SQLITE_CACHE_KIB: Final = 8192
SQLITE_JOURNAL_MODE: Final = "wal"
SQLITE_SYNCHRONOUS: Final = "FULL"
SQLITE_TEMP_STORE: Final = "FILE"
TRANSACTION_BEGIN: Final = "BEGIN IMMEDIATE"
TRANSACTION_COMMIT: Final = "COMMIT"
TRANSACTION_ROLLBACK: Final = "ROLLBACK"

# Filesystem operations
HASH_CHUNK_BYTES: Final = 1024 * 1024
PRIVATE_DIRECTORY_MODE: Final = 0o700
PRIVATE_FILE_MODE: Final = 0o600
READ_BINARY: Final = "rb"

# Text encoding and serialization
TEXT_ENCODING: Final = "utf-8"
JSON_SEPARATORS: Final = (",", ":")

# Pipeline configuration and secrets
CONFIGURATION_FILENAME: Final = "redactor.toml"
PIPELINE_VERSION: Final = "pipeline-v1"
MAPPING_KEY_ENVIRONMENT: Final = "REDACTOR_SECRET_KEY"
MODEL_KEY_ENVIRONMENT: Final = "LLM_API_KEY"
MODEL_URL_ENVIRONMENT: Final = "LLM_BASE_URL"
MODEL_NAME_ENVIRONMENT: Final = "LLM_MODEL"
MODEL_ENABLED_ENVIRONMENT: Final = "LLM_ENABLED"
ENVIRONMENT_TRUE: Final = ("1", "true", "yes")
ENVIRONMENT_FALSE: Final = ("0", "false", "no")
SECRET_KEY_BYTES: Final = 32
MODEL_DIRECTORY: Final = ".models"

# Model adapters and initial resource limits
NER_SPACY: Final = "spacy"
NER_GLINER: Final = "gliner"
OCR_TESSERACT: Final = "tesseract"
OCR_PPOCR: Final = "ppocr"
DEFAULT_SPACY_MODEL: Final = "en_core_web_sm"
DEFAULT_OCR_LANGUAGE: Final = "eng"
DEFAULT_MODEL_BUDGET_USD: Final = "3.00"
DEFAULT_MODEL_ATTEMPTS: Final = 3
DEFAULT_MODEL_TIMEOUT_SECONDS: Final = 15.0
DEFAULT_MODEL_DEADLINE_SECONDS: Final = 45.0
DEFAULT_CIRCUIT_FAILURES: Final = 3
DEFAULT_CIRCUIT_COOLDOWN_SECONDS: Final = 60.0
DEFAULT_MODEL_OUTPUT_TOKENS: Final = 1024
DEFAULT_MODEL_INPUT_BYTES: Final = 16384
DEFAULT_RECORD_BYTES: Final = 1024 * 1024
DEFAULT_CHUNK_BYTES: Final = 4 * 1024 * 1024
DEFAULT_IMAGE_PIXELS: Final = 16_000_000
DEFAULT_NESTING_DEPTH: Final = 16
DEFAULT_DATE_SHIFT_DAYS: Final = 365
DEFAULT_CHECKPOINT_RECORDS: Final = 5000
