"""Stable failure codes safe to persist without raw input or exception text."""

from typing import Final

ERROR_UNSUPPORTED_SCHEMA: Final = "unsupported_state_schema"
ERROR_INVALID_MIGRATIONS: Final = "invalid_migration_sequence"
ERROR_MIGRATION_TRANSACTION_REQUIRED: Final = "migration_transaction_required"
ERROR_INCOMPLETE_MIGRATION: Final = "incomplete_migration_statement"
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
ERROR_CONFIGURATION: Final = "invalid_pipeline_configuration"
ERROR_MAPPING_KEY: Final = "invalid_mapping_key"
ERROR_STEP_RESULT: Final = "unaccepted_step_result"
ERROR_VERIFICATION: Final = "verification_did_not_pass"
ERROR_VERIFICATION_RECORD: Final = "invalid_verification_record"
ERROR_VERIFICATION_CONTEXT: Final = "verification_context_mismatch"
ERROR_CHECK_MISSING: Final = "required_verification_check_missing"
ERROR_COVERAGE: Final = "incomplete_surface_coverage"
ERROR_CLINICAL_CHANGED: Final = "clinical_content_changed"
ERROR_RESIDUAL_PHI: Final = "residual_phi_detected"
ERROR_STRUCTURE: Final = "invalid_native_structure"
ERROR_REPLACEMENT: Final = "expected_replacement_missing"
ERROR_PIXELS: Final = "pixel_verification_incomplete"
ERROR_UNKNOWN_STEP: Final = "unknown_pipeline_step"
ERROR_PIPELINE_BLOCKED: Final = "pipeline_dependencies_blocked"

VERIFICATION_REASON_CODES: Final = (
    ERROR_CHECK_MISSING,
    ERROR_COVERAGE,
    ERROR_CLINICAL_CHANGED,
    ERROR_RESIDUAL_PHI,
    ERROR_STRUCTURE,
    ERROR_REPLACEMENT,
    ERROR_PIXELS,
    ERROR_TIMEOUT,
    ERROR_PROCESSING,
)

# Coordinator startup and input discovery
ERROR_RUN_ACTIVE: Final = "state_directory_in_use"
ERROR_INPUT_DIRECTORY: Final = "invalid_input_directory"
ERROR_DIRECTORY_OVERLAP: Final = "input_and_runtime_directories_overlap"
ERROR_INPUT_ENTRY: Final = "unsupported_input_entry"
ERROR_WORKER_FAILED: Final = "worker_failed"
ERROR_COORDINATOR_FAILED: Final = "coordinator_failed"

COORDINATOR_FAILURE_CODES: Final = (
    ERROR_RUN_ACTIVE,
    ERROR_INPUT_DIRECTORY,
    ERROR_DIRECTORY_OVERLAP,
    ERROR_INPUT_ENTRY,
    ERROR_INPUT_CHANGED,
    ERROR_UNSUPPORTED_SCHEMA,
    ERROR_INVALID_MIGRATIONS,
    ERROR_WAL_UNAVAILABLE,
    ERROR_WORKER_FAILED,
)

FAILURE_CODES: Final = (
    ERROR_VERIFICATION,
    ERROR_VERIFICATION_CONTEXT,
    ERROR_VERIFICATION_RECORD,
    ERROR_STEP_RESULT,
    ERROR_PROCESSING,
    ERROR_TIMEOUT,
    ERROR_INPUT_CHANGED,
    ERROR_OUTPUT_CONFLICT,
    ERROR_OUTPUT_FILESYSTEM,
    ERROR_ARTIFACT_MISSING,
    ERROR_ARTIFACT_CORRUPT,
    ERROR_INVALID_CHECKPOINT,
    ERROR_INCOMPLETE_INPUT,
)
