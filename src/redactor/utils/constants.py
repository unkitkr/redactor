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

# Durable pipeline steps and verification
STEP_INSPECT: Final = "inspect"
STEP_ANALYZE: Final = "analyze"
STEP_RESOLVE: Final = "resolve"
STEP_REWRITE: Final = "rewrite"
STEP_VERIFY: Final = "verify"
STEP_PUBLISH: Final = "publish"
STEP_QUARANTINE: Final = "quarantine"
STEP_RECONCILE: Final = "reconcile"
VERIFIER_VERSION: Final = "verifier-v1"
VERIFICATION_PASS: Final = "pass"
VERIFICATION_FAIL: Final = "fail"
VERIFICATION_UNKNOWN: Final = "unknown"
CHECK_STRUCTURE: Final = "structure"
CHECK_COVERAGE: Final = "coverage"
CHECK_TRANSFORMATIONS: Final = "transformations"
CHECK_RESIDUAL_PHI: Final = "residual_phi"
CHECK_CLINICAL: Final = "clinical"
CHECK_PIXELS: Final = "pixels"
REQUIRED_VERIFICATION_CHECKS: Final = (
    CHECK_STRUCTURE,
    CHECK_COVERAGE,
    CHECK_TRANSFORMATIONS,
    CHECK_RESIDUAL_PHI,
    CHECK_CLINICAL,
)
SHA256_PATTERN: Final = r"^[0-9a-f]{64}$"
MAX_MANIFEST_BYTES: Final = 4 * 1024 * 1024

# Frozen run inventory
RUNS_DIRECTORY: Final = "runs"
RUN_MANIFEST_FILENAME: Final = "manifest.json"
RUN_MANIFEST_PENDING_FILENAME: Final = "manifest.part"
STATE_KEY_CONTEXT: Final = b"redactor-state-key-v1"

# Private evidence envelopes
ENCRYPTION_KEY_CONTEXT: Final = b"redactor-private-evidence-v1:"
ENCRYPTION_HEADER: Final = b"RDE1"
ENCRYPTION_NONCE_BYTES: Final = 12
ENCRYPTION_TAG_BYTES: Final = 16
MAX_PRIVATE_RECORD_BYTES: Final = 4 * 1024 * 1024

# Model accounting and bounded transport
MODEL_RESERVED: Final = "reserved"
MODEL_SETTLED: Final = "settled"
MODEL_UNCERTAIN: Final = "uncertain"
MODEL_REMOTE: Final = "remote"
MODEL_LOCAL: Final = "local"
NANOS_PER_DOLLAR: Final = 1_000_000_000
TOKENS_PER_MILLION: Final = 1_000_000
MODEL_RESPONSE_BYTES: Final = 64 * 1024
MODEL_ENVELOPE_TOKENS: Final = 1024
MODEL_REQUEST_CONTEXT: Final = b"redactor-model-request-v1:"
MODEL_RETRY_BASE_SECONDS: Final = 0.5
MODEL_FINISH_STOP: Final = "stop"
MODEL_PURPOSE_JUDGE: Final = "judge"
HTTP_RETRY_AFTER_HEADER: Final = "retry-after"
HTTP_CONTENT_ENCODING_HEADER: Final = "content-encoding"
HTTP_IDENTITY_ENCODING: Final = "identity"

# Native delimited text
CSV_ADAPTER_VERSION: Final = "csv-utf8-v1"
CSV_DELIMITERS: Final = (",", "\t", ";")
CSV_SNIFF_BYTES: Final = 64 * 1024
UTF8_BOM: Final = b"\xef\xbb\xbf"
LINE_ENDING_LF: Final = "\n"
LINE_ENDING_CRLF: Final = "\r\n"
