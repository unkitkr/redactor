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
DEFAULT_NER_MAX_CHARACTERS: Final = 16_384
DEFAULT_NER_CACHE_ENTRIES: Final = 512
DEFAULT_NER_CACHE_CHARACTERS: Final = 1024
MAX_TEXT_ENTITIES: Final = 512
SPACY_NER_COMPONENT: Final = "ner"
SPACY_EXCLUDED_COMPONENTS: Final = (
    "tagger",
    "parser",
    "lemmatizer",
    "attribute_ruler",
    "senter",
)
ENTITY_PERSON: Final = "person"
ENTITY_ORGANIZATION: Final = "organization"
ENTITY_LOCATION: Final = "location"
ENTITY_DATE: Final = "date"
ENTITY_TIME: Final = "time"
SPACY_ENTITY_TYPES: Final = (
    ("PERSON", ENTITY_PERSON),
    ("ORG", ENTITY_ORGANIZATION),
    ("GPE", ENTITY_LOCATION),
    ("LOC", ENTITY_LOCATION),
    ("FAC", ENTITY_LOCATION),
    ("DATE", ENTITY_DATE),
    ("TIME", ENTITY_TIME),
)
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
DEFAULT_RETRY_INITIAL_SECONDS: Final = 0.5
DEFAULT_RETRY_MAX_SECONDS: Final = 8.0
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

# Native format recognition and parser limits
FORMAT_UNKNOWN: Final = "unknown"
FORMAT_ZIP: Final = "zip"
FORMAT_DOCX: Final = "docx"
FORMAT_XLSX: Final = "xlsx"
FORMAT_OLE: Final = "ole"
FORMAT_PDF: Final = "pdf"
FORMAT_DICOM: Final = "dicom"
FORMAT_JPEG: Final = "jpeg"
FORMAT_PNG: Final = "png"
FORMAT_TIFF: Final = "tiff"
FORMAT_JSON: Final = "json"
FORMAT_FHIR: Final = "fhir"
FORMAT_HL7: Final = "hl7"
FORMAT_CSV: Final = "csv"
FORMAT_TSV: Final = "tsv"
FORMAT_TEXT: Final = "text"
FORMAT_PROBE_BYTES: Final = 4096
ZIP_SIGNATURE: Final = b"PK\x03\x04"
ZIP_END_SIGNATURE: Final = b"PK\x05\x06"
ZIP_END_RECORD_BYTES: Final = 22
ZIP_MAX_COMMENT_BYTES: Final = 65535
ZIP_MAX_ENTRIES: Final = 20000
ZIP_MAX_DIRECTORY_BYTES: Final = 8 * 1024 * 1024
ZIP_ENCRYPTED_FLAG: Final = 1
DEFAULT_NATIVE_FILE_BYTES: Final = 32 * 1024 * 1024
DEFAULT_ARCHIVE_BYTES: Final = 256 * 1024 * 1024
OOXML_CONTENT_TYPES: Final = "[Content_Types].xml"
OOXML_PACKAGE_RELATIONSHIPS: Final = "_rels/.rels"
OOXML_CONTENT_NAMESPACE: Final = (
    "http://schemas.openxmlformats.org/package/2006/content-types"
)
OOXML_OVERRIDE_TAG: Final = f"{{{OOXML_CONTENT_NAMESPACE}}}Override"
OOXML_TYPES_TAG: Final = f"{{{OOXML_CONTENT_NAMESPACE}}}Types"
OOXML_RELATIONSHIP_NAMESPACE: Final = (
    "http://schemas.openxmlformats.org/package/2006/relationships"
)
OOXML_RELATIONSHIPS_TAG: Final = f"{{{OOXML_RELATIONSHIP_NAMESPACE}}}Relationships"
OOXML_RELATIONSHIP_TAG: Final = f"{{{OOXML_RELATIONSHIP_NAMESPACE}}}Relationship"
OOXML_RELATIONSHIP_ID: Final = "Id"
OOXML_RELATIONSHIP_TYPE: Final = "Type"
OOXML_OFFICE_DOCUMENT_RELATIONSHIP: Final = (
    "http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument"
)
OOXML_RELATIONSHIP_TARGET: Final = "Target"
OOXML_RELATIONSHIP_MODE: Final = "TargetMode"
OOXML_EXTERNAL_MODE: Final = "External"
DOCX_ROOT_TAG: Final = (
    "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}document"
)
XLSX_ROOT_TAG: Final = (
    "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}workbook"
)
OOXML_PART_ATTRIBUTE: Final = "PartName"
OOXML_TYPE_ATTRIBUTE: Final = "ContentType"
DOCX_MAIN_PART: Final = "word/document.xml"
XLSX_MAIN_PART: Final = "xl/workbook.xml"
DOCX_MAIN_TYPE: Final = (
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"
)
XLSX_MAIN_TYPE: Final = (
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"
)
XML_SUFFIXES: Final = (".xml", ".rels")
PDF_SIGNATURE: Final = b"%PDF-"
OLE_SIGNATURE: Final = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"
DICOM_SIGNATURE: Final = b"DICM"
DICOM_PREAMBLE_BYTES: Final = 128
JPEG_SIGNATURE: Final = b"\xff\xd8\xff"
PNG_SIGNATURE: Final = b"\x89PNG\r\n\x1a\n"
TIFF_SIGNATURES: Final = (b"II*\x00", b"MM\x00*")
HL7_SIGNATURE: Final = b"MSH"
LEGACY_TEXT_ENCODING: Final = "cp1252"
UTF8_BOM_ENCODING: Final = "utf-8-sig"
TEXT_ALLOWED_CONTROLS: Final = (9, 10, 12, 13)
JSON_RESOURCE_TYPE: Final = "resourceType"
FHIR_BUNDLE_TYPE: Final = "Bundle"
JSON_START_MAP: Final = "start_map"
JSON_END_MAP: Final = "end_map"
JSON_MAP_KEY: Final = "map_key"
JSON_START_ARRAY: Final = "start_array"
JSON_END_ARRAY: Final = "end_array"
JSON_STRING: Final = "string"
JSON_SCALAR_DELIMITERS: Final = b" \t\r\n,:{}[]"

# Scoped pseudonyms and conservative identity normalization
PSEUDONYM_KEY_CONTEXT: Final = b"redactor-pseudonym-v1:"
UNICODE_NORMAL_FORM: Final = "NFKC"
NAME_TITLES: Final = ("dr", "doctor", "mr", "mrs", "ms", "miss", "prof", "professor")
IDENTIFIER_DIGITS: Final = 18
PRODUCT_LOT_NAMESPACE: Final = "product-lot"
NPI_NAMESPACE: Final = "provider-npi"
NPI_BASE_DIGITS: Final = 9
NPI_PREFIX_CHOICES: Final = ("1", "2")
NPI_LUHN_PREFIX_SUM: Final = 24

# Corroborated identity evidence and opaque database indexes
IDENTITY_PROVIDER: Final = "provider"
IDENTITY_CORROBORATED: Final = "corroborated"
IDENTITY_ISOLATED: Final = "isolated"
IDENTITY_AMBIGUOUS: Final = "ambiguous"
IDENTITY_IDENTIFIER_NAMESPACE: Final = "identity-identifier"
IDENTITY_NAME_NAMESPACE: Final = "identity-name"
IDENTITY_BIRTH_NAMESPACE: Final = "identity-birth-date"
IDENTITY_OBSERVATION_NAMESPACE: Final = "identity-observation"

# Calendar-date spelling and older-age generalization
DATE_OFFSET_NAMESPACE: Final = "patient-date-offset"
DATE_STYLE_YMD: Final = "ymd"
DATE_STYLE_MDY: Final = "mdy"
DATE_STYLE_COMPACT: Final = "compact"
DATE_ZONE_PATTERN: Final = r"(?:[+-](?:[01][0-9]|2[0-3]):?[0-5][0-9])"
DATE_CLOCK_PATTERN: Final = (
    r"(?P<clock>[ T][0-9]{2}:[0-9]{2}(?::[0-9]{2}(?:\.[0-9]{1,6})?)?"
    r"(?:Z|" + DATE_ZONE_PATTERN + r")?)?"
)
DATE_YMD_PATTERN: Final = (
    r"(?P<year>[0-9]{4})(?P<separator>[-/])(?P<month>[0-9]{1,2})"
    r"(?P=separator)(?P<day>[0-9]{1,2})" + DATE_CLOCK_PATTERN
)
DATE_MDY_PATTERN: Final = (
    r"(?P<month>[0-9]{1,2})(?P<separator>/)(?P<day>[0-9]{1,2})/"
    r"(?P<year>[0-9]{4})" + DATE_CLOCK_PATTERN
)
DATE_COMPACT_PATTERN: Final = (
    r"(?P<year>[0-9]{4})(?P<month>[0-9]{2})(?P<day>[0-9]{2})"
    r"(?P<clock>[0-9]{2}(?:[0-9]{2}(?:[0-9]{2}(?:\.[0-9]{1,6})?)?)?"
    r"(?:[+-](?:[01][0-9]|2[0-3])[0-5][0-9])?)?"
)
AGE_GROUP_MINIMUM: Final = 90
AGE_GROUP_LABEL: Final = "90+"
BIRTH_BOUND_TEMPLATE: Final = "on or before {year}"

# ZIP3 suppression list published in HHS de-identification guidance
ZIP_CODE_PATTERN: Final = r"[0-9]{3}(?:[0-9]{2}(?:-?[0-9]{4})?)?"
ZIP_REDACTED_PREFIX: Final = "000"
RESTRICTED_ZIP_PREFIXES: Final = (
    "036",
    "059",
    "063",
    "102",
    "203",
    "556",
    "692",
    "790",
    "821",
    "823",
    "830",
    "831",
    "878",
    "879",
    "884",
    "890",
    "893",
)
