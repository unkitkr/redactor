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
OUTPUT_OWNER_FILENAME: Final = ".run-id"
PUBLISHED_DIRECTORY: Final = "published"
TEMPORARY_DIRECTORY: Final = "tmp"
TEMPORARY_FILE_TEMPLATE: Final = "{attempt_token}.part"
RESULT_FILE_TEMPLATE: Final = "{attempt_token}.result"
REASON_FILE_SUFFIX: Final = ".reason.json"
REPORT_FILENAME: Final = "report.json"
RUN_LOG_FILENAME: Final = "run.log"
OUTCOME_PUBLISHED: Final = "published"
OUTCOME_QUARANTINED: Final = "quarantined"
QUARANTINE_DIRECTORY: Final = "quarantine"
FILE_LOCATION_FIELDS: Final = ("temporary_directory", "output_path")

# Coordinator ownership and placeholder work
RUN_LOCK_FILENAME: Final = "coordinator.lock"
PRINT_TASK_STEP: Final = "print_task"
BOOTSTRAP_PROCESSING_VERSION: Final = "bootstrap-v1"

# Worker processes and exit status
WORKER_MODULE: Final = "redactor.workers"
WORKER_FAILURE_FILENAME: Final = "worker-failure-{pid}.json"
FAILURE_SQLITE: Final = "sqlite"
FAILURE_FILESYSTEM: Final = "filesystem"
FAILURE_MEMORY: Final = "memory"
FAILURE_VALIDATION: Final = "validation"
FAILURE_UNEXPECTED: Final = "unexpected"
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
PIPELINE_VERSION: Final = "pipeline-v25"
RUNTIME_SOURCE_SUFFIXES: Final = (".py", ".sql")
RUNTIME_IGNORED_SUFFIXES: Final = (".pyc", ".pyo")
RUNTIME_MISSING_ARTIFACT: Final = "missing"
RUNTIME_PACKAGES: Final = (
    "cryptography",
    "defusedxml",
    "httpx",
    "ijson",
    "numpy",
    "lxml",
    "onnxruntime",
    "openai",
    "openpyxl",
    "opencv-python-headless",
    "pillow",
    "pydantic",
    "pydicom",
    "pymupdf",
    "rapidocr",
    "spacy",
    "tokenizers",
    "zxing-cpp",
)
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
ENTITY_IDENTIFIER: Final = "identifier"
ENTITY_LOCATION: Final = "location"
ENTITY_DATE: Final = "date"
ENTITY_TIME: Final = "time"
ENTITY_AGE: Final = "age"
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
MODEL_PROVIDER_OPENAI: Final = "openai"
MODEL_PROVIDER_OPENROUTER: Final = "openrouter"
DEFAULT_MODEL_TEMPERATURE: Final = 0.0
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
INFERENCE_STEPS: Final = (STEP_ANALYZE, STEP_REWRITE, STEP_VERIFY)
VERIFIER_VERSION: Final = "verifier-v19"
VERIFIER_RESIDUAL_PATTERNS: Final = (
    r"(?i)\b[\w.+-]+@[\w.-]+\.[a-z]{2,}\b",
    r"(?<!\d)(?:\+?1[ .-]?)?(?:\(\d{3}\)|\d{3})[ .-]\d{3}[ .-]\d{4}(?!\d)",
    r"\b\d{3}-\d{2}-\d{4}\b",
    r"\b(?:\d{1,3}\.){3}\d{1,3}\b",
    r"(?i)\b(?:https?://|www\.)\S+",
    r"\b\d{4}[-/]\d{1,2}[-/]\d{1,2}\b",
    r"\b\d{1,2}[-/]\d{1,2}[-/]\d{2,4}\b",
    r"(?i)\b(?:MRN|SSN|account|serial|license)\s*[:#]?\s*"
    r"(?P<value>[A-Z0-9][\w-]+)",
    r"(?i)\broom(?:[ \t]*[:#][ \t]*|[ \t]+"
    r"(?!with\b|for\b|has\b|is\b|was\b|the\b|a\b|an\b))"
    r"(?P<value>[A-Z0-9][\w-]+)",
    r"(?i:\b(?:daughter|son|husband|wife|spouse|mother|father|Dr\.))\s+"
    r"(?P<value>(?:[A-ZÀ-ÖØ-Þ]\.(?=\s+[A-ZÀ-ÖØ-Þ])|[A-ZÀ-ÖØ-Þ][\w'’\-]*)"
    r"(?:\s+(?:[A-ZÀ-ÖØ-Þ]\.(?=\s+[A-ZÀ-ÖØ-Þ])|[A-ZÀ-ÖØ-Þ][\w'’\-]*)){0,3})",
)
# These independently locate suspicious values, not permission to rewrite them.
VERIFIER_LABELLED_VALUE_PATTERN: Final = (
    r"(?i:\b(?:patient(?:[ \t]+name)?|name|attending|provider|mother|father|"
    r"daughter|son|spouse|guardian|caregiver|next of kin|facility|hospital|"
    r"clinic|phone|telephone|tel|mobile|fax)[ \t]*:[ \t]*)"
    r"(?P<value>[^\r\n;|]+)"
)
VERIFIER_LABEL_VALUE_END_PATTERN: Final = r"(?<=[^\W\d_]{2})\.(?=[ \t]|$)|[ \t]{2,}"
VERIFIER_FACILITY_PATTERN: Final = (
    r"\b(?:[A-ZÀ-ÖØ-Þ][\w'’\-]*[ \t]+)+"
    r"(?:Hospital|Clinic|Centre|Center|Laboratory)\b"
)
VERIFIER_CONTACT_CANDIDATE_PATTERN: Final = (
    r"(?<![\w+])(?P<number>(?:\+|00)?\d(?:[\d \t().-]*\d))"
    r"(?:[ \t]*(?i:ext(?:ension)?\.?|x|#)[ \t]*[:=]?[ \t]*\d+)?(?!\w)"
)
VERIFIER_CONTACT_MINIMUM_DIGITS: Final = 7
VERIFIER_CONTACT_INTERNATIONAL_PREFIXES: Final = ("+", "00")
VERIFIER_SIGNED_DECIMAL_PATTERN: Final = r"\+[0-9]+\.[0-9]+"
VERIFIER_RELATIVE_TIME_PATTERN: Final = (
    r"(?i)\b(?:age[ \t]+)?[0-9]+(?:\.[0-9]+)?[ \t]+"
    r"(?:days?|weeks?|months?|years?)(?:[ \t]+ago)?\b"
)
VERIFIER_IPV6_CANDIDATE_PATTERN: Final = (
    r"(?<![\w:])[0-9A-Fa-f:.]*:[0-9A-Fa-f:.]+"
    r"(?:%[A-Za-z0-9_.-]+)?(?![\w:])"
)
VERIFIER_NAME_BOUNDARY_START: Final = r"(?<![\w'’\-])"
VERIFIER_NAME_BOUNDARY_END: Final = r"(?![\w'’\-])"
VERIFIER_NAME_APOSTROPHE_PATTERN: Final = r"['’]"
VERIFIER_MENTION_ROLE: Final = (
    r"(?:patient|Pt\.?|daughter|son|husband|wife|spouse|mother|father|sister|brother|"
    r"partner|caregiver|guardian|doctor|Dr\.?|Prof\.?)"
)
VERIFIER_ROLE_CONNECTOR: Final = r"(?:with|w/|to|from|by)[ \t]+(?:the[ \t]+)?"
VERIFIER_MENTION_PREFIX_PATTERN: Final = (
    rf"(?i)(?:{VERIFIER_ROLE_CONNECTOR})?{VERIFIER_MENTION_ROLE}[ \t]+"
)
VERIFIER_EDIT_JOIN_PATTERN: Final = r"(?i)[ \t]*(?:(?:[,;&]|and)[ \t]*)*"
VERIFIER_SURFACE_PUNCTUATION: Final = r"[ \t,.;:!?]*"
VERIFIER_MENTION_SUFFIX_PATTERN: Final = (
    rf"(?i)[ \t]+(?:&|and)[ \t]+{VERIFIER_MENTION_ROLE}(?:-in-law)?(?=[ \t,.;:]|$)"
)
VERIFIER_ROLE_LABEL_PATTERN: Final = (
    rf"(?i)\b{VERIFIER_MENTION_ROLE}(?=[ \t]*:|[ \t]+(?:is|was|aged)[ \t]+"
    r"[0-9]{1,3}\+?[ \t]+years?[ \t]+old\b)"
)
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
MAX_SQLITE_INTEGER: Final = (1 << 63) - 1
TOKENS_PER_MILLION: Final = 1_000_000
MODEL_RESPONSE_BYTES: Final = 64 * 1024
MODEL_ENVELOPE_TOKENS: Final = 1024
MODEL_REQUEST_CONTEXT: Final = b"redactor-model-request-v1:"
DEFAULT_RETRY_INITIAL_SECONDS: Final = 0.5
DEFAULT_RETRY_MAX_SECONDS: Final = 8.0
MODEL_FINISH_STOP: Final = "stop"
MODEL_PURPOSE_DETECTOR: Final = "detector"
MODEL_PURPOSE_JUDGE: Final = "judge"
HTTP_RETRY_AFTER_HEADER: Final = "retry-after"
HTTP_CONTENT_ENCODING_HEADER: Final = "content-encoding"
HTTP_IDENTITY_ENCODING: Final = "identity"

# Grounded text detection
DETECTOR_PROMPT_VERSION: Final = "text-entities-v2"
DETECTOR_OBSERVATION_CONTEXT: Final = b"redactor-detection-observation-v1:"
DETECTOR_TEXT_FIELD: Final = "text"

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
IMAGE_FORMATS: Final = (FORMAT_JPEG, FORMAT_PNG, FORMAT_TIFF)
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
ZIP_LOCAL_HEADER_FORMAT: Final = "<4s5H3I2H"
ZIP_CENTRAL_HEADER_BYTES: Final = 46
ZIP_END_RECORD_FORMAT: Final = "<4s4H2IH"
ZIP_UTF8_FLAG: Final = 0x800
ZIP_LEGACY_ENCODING: Final = "cp437"
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
JSON_NUMBER_PATTERN: Final = r"-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?"
JSON_ROOT_LOCATION: Final = ("json",)
JSON_KEY_LOCATION: Final = "key"
JSON_VALUE_LOCATION: Final = "value"
JSON_EMBEDDED_LOCATION: Final = "embedded"
JSON_BASE64_ENCODING: Final = "base64"
JSON_MEDIA_TYPE: Final = "application/json"
JSON_PROVIDER_CONTAINERS: Final = (
    "provider",
    "rendering_provider",
    "attending",
    "practitioner",
    "physician",
)
JSON_PATIENT_CONTAINERS: Final = ("patient", "subscriber", "member")
JSON_NAME_COMPONENTS: Final = ("family", "given", "prefix", "suffix")
JSON_FIELD_ALIASES: Final = (
    ("birthdate", "birth_date"),
    ("dob", "birth_date"),
    ("postalcode", "postal_code"),
    ("postal_code", "zip"),
    ("service_date", "date"),
    ("last_login_ip", "ip_address"),
    ("last_login_ipv6", "ip_address"),
    ("session_url", "url"),
    ("line", "address"),
    ("city", "city"),
)
JSON_IDENTIFIER_KEYS: Final = (
    "id",
    "claim_id",
    "member_id",
    "subscriber_id",
    "account_id",
    "record_id",
    "encounter_id",
    "policy_number",
    "accession_number",
)
JSON_QUANTITY_KEYS: Final = (
    "amount",
    "record_count",
    "count",
    "quantity",
    "total",
    "price",
    "charge",
)
SURROGATE_INITIAL_ALPHABET: Final = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
JSON_DATE_KEYS: Final = (
    "date",
    "service_date",
    "admit_ts",
    "discharge_ts",
    "encounter_date",
    "timestamp",
    "admit_date",
    "discharge_date",
)

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
IDENTITY_BATCH_NAMESPACE: Final = "identity-observation-batch"
IDENTITY_BATCH_LIMIT: Final = 20_000
IDENTITY_CANDIDATE_LIMIT: Final = 512
IDENTITY_STORAGE_CONTEXT: Final = "identity-observation:{task_id}:{observation_key}"
IDENTITY_COHORT_CONTEXT: Final = "identity-cohort:{task_id}:{identity_key}"
IDENTITY_SNAPSHOT_NAMESPACE: Final = "identity-snapshot-v1"
IDENTITY_BINDING_NAMESPACE: Final = "identity-binding-v1"
IDENTITY_RESOLUTION_BATCH_SIZE: Final = 1000
IDENTITY_LOOKUP_CACHE_ENTRIES: Final = 512

# Realistic surrogate vocabulary, independent of the supplied input values
PERSON_NAME_NAMESPACE: Final = "person-name"
PHONE_NAMESPACE: Final = "phone"
EMAIL_NAMESPACE: Final = "email"
ADDRESS_NAMESPACE: Final = "street-address"
SSN_NAMESPACE: Final = "social-security-number"
SURROGATE_DOMAIN: Final = "example.org"
SURROGATE_GIVEN_NAMES: Final = (
    "Avery",
    "Blair",
    "Casey",
    "Devon",
    "Ellis",
    "Finley",
    "Harper",
    "Jamie",
    "Jordan",
    "Kendall",
    "Lane",
    "Morgan",
    "Parker",
    "Quinn",
    "Reese",
    "Robin",
    "Rowan",
    "Sage",
    "Shiloh",
    "Skyler",
    "Taylor",
    "Terry",
    "Toby",
    "Wren",
)
SURROGATE_FAMILY_PREFIXES: Final = (
    "Ash",
    "Bram",
    "Cedar",
    "Dale",
    "Elm",
    "Fair",
    "Glen",
    "Haven",
    "Lang",
    "Mill",
    "North",
    "Oak",
    "Pine",
    "Raven",
    "Rose",
    "West",
)
SURROGATE_FAMILY_SUFFIXES: Final = (
    "brook",
    "bury",
    "dale",
    "field",
    "ford",
    "grove",
    "ham",
    "haven",
    "hurst",
    "land",
    "ley",
    "mont",
    "ridge",
    "ton",
    "well",
    "wood",
)
SURROGATE_STREET_SUFFIX: Final = "Road"
NANP_PHONE_DIGITS: Final = 10
NANP_COUNTRY_CODE: Final = "1"
NANP_NUMBER_BLOCK: Final = 800
NANP_MINIMUM_PREFIX: Final = 200
PHONE_LINE_NUMBER_SPACE: Final = 10_000
SURROGATE_STREET_NUMBER_SPACE: Final = 9900
SURROGATE_STREET_NUMBER_MINIMUM: Final = 100

# Pixel carriers and locally pinned face detection.
PIXEL_TEXT: Final = "text"
PIXEL_BARCODE: Final = "barcode"
PIXEL_FACE: Final = "face"
PIXEL_MASK_PADDING: Final = 2
PIXEL_MASK_HEIGHT_MARGIN: Final = 0.25
PIXEL_MASK_COLOR: Final = 0
PIXEL_MAXIMUM_FRAMES: Final = 256
PIXEL_JPEG_QUALITY: Final = 100
PIXEL_IMAGE_MODES: Final = ("RGB", "L", "P")
PIXEL_RGB_MODE: Final = "RGB"
PIXEL_TEMPORARY_FILENAME: Final = "frame.png"
PIXEL_PNG_FORMAT: Final = "PNG"
PIXEL_JPEG_FORMAT: Final = "JPEG"
PIXEL_TIFF_FORMAT: Final = "TIFF"
PIXEL_TIFF_COMPRESSION: Final = "tiff_deflate"
NATIVE_IMAGE_LOCATION: Final = "image"
DOCX_WORD_NAMESPACE: Final = (
    "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
)
DOCX_TEXT_TAGS: Final = (
    f"{{{DOCX_WORD_NAMESPACE}}}t",
    f"{{{DOCX_WORD_NAMESPACE}}}delText",
)
DOCX_PARAGRAPH_TAG: Final = f"{{{DOCX_WORD_NAMESPACE}}}p"
DOCX_INSTRUCTION_TAG: Final = f"{{{DOCX_WORD_NAMESPACE}}}instrText"
DOCX_IMAGE_SUFFIXES: Final = (".png", ".jpg", ".jpeg", ".tif", ".tiff")
DOCX_TECHNICAL_ATTRIBUTES: Final = (
    "Id",
    "Type",
    "TargetMode",
    "ContentType",
    "Extension",
    "PartName",
    "space",
    "Ignorable",
    "Requires",
    "embed",
    "link",
)
DICOM_UID_NAMESPACE: Final = "dicom_uid"
DICOM_UID_PREFIX: Final = "2.25."
DICOM_IDENTITY_FIELDS: Final = (
    ("ImplementationVersionName", "identifier", "dicom_implementation"),
    ("InstitutionName", "organization", "organization"),
    ("PatientName", "patient_name", ""),
    ("PatientID", "patient_id", "mrn"),
    ("PatientBirthDate", "birth_date", ""),
    ("PatientAddress", "address", ""),
    ("PatientTelephoneNumbers", "phone", ""),
    ("InstitutionAddress", "address", ""),
    ("AccessionNumber", "identifier", "accession"),
    ("ScheduledProcedureStepID", "identifier", "procedure_step"),
    ("RequestedProcedureID", "identifier", "procedure_request"),
)
DICOM_TEXT_VRS: Final = (
    "AE",
    "AS",
    "CS",
    "DA",
    "DT",
    "LO",
    "LT",
    "PN",
    "SH",
    "ST",
    "TM",
    "UC",
    "UI",
    "UR",
    "UT",
)
DICOM_SCHEMA_UID_FIELDS: Final = (
    "SOPClassUID",
    "ReferencedSOPClassUID",
    "TransferSyntaxUID",
    "ImplementationClassUID",
    "MediaStorageSOPClassUID",
)
DICOM_PIXEL_LOCATION: Final = "dicom_pixel"
DICOM_PIXEL_TAG: Final = 0x7FE00010
YUNET_DIRECTORY: Final = "yunet"
YUNET_FILENAME: Final = "face_detection_yunet_2026may.onnx"
YUNET_SHA256: Final = "ebafce4e3c118d6554634be5c27ab333b4c047a9a8c3faf1d7cf93101c22f0f0"
YUNET_TILE_SIZE: Final = 640
YUNET_TILE_OVERLAP: Final = 320
YUNET_MAXIMUM_CANDIDATES: Final = 5000
YUNET_SCORE_THRESHOLD: Final = 0.6
YUNET_NMS_THRESHOLD: Final = 0.3

# Typed tabular fields. Unknown columns still require text analysis.
FIELD_PATIENT_NAME: Final = "patient_name"
FIELD_PROVIDER_NAME: Final = "provider_name"
FIELD_PATIENT_ID: Final = "patient_id"
FIELD_PROVIDER_ID: Final = "provider_id"
FIELD_IDENTIFIER: Final = "identifier"
FIELD_BIRTH_DATE: Final = "birth_date"
FIELD_DATE: Final = "date"
FIELD_AGE: Final = "age"
FIELD_PHONE: Final = "phone"
FIELD_EMAIL: Final = "email"
FIELD_ADDRESS: Final = "address"
FIELD_ZIP: Final = "zip"
FIELD_LOT: Final = "lot"
FIELD_CLINICAL: Final = "clinical"
FIELD_TEXT: Final = "text"
FIELD_ORGANIZATION: Final = "organization"
LAB_DESCRIPTION_NAMESPACE: Final = "laboratory-description"
FIELD_LOCATION: Final = "location"
FIELD_NETWORK: Final = "network"
FIELD_WEB: Final = "web"
XLSX_NAMESPACE: Final = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
XLSX_WORKSHEET_PREFIX: Final = "xl/worksheets/sheet"
XLSX_SHARED_STRINGS: Final = "xl/sharedStrings.xml"
XLSX_STYLES: Final = "xl/styles.xml"
XLSX_WORKBOOK: Final = "xl/workbook.xml"
XLSX_DATE_FORMAT_IDS: Final = (14, 15, 16, 17, 22, 27, 30, 36, 50, 57)
XLSX_EPOCH: Final = (1899, 12, 30)
XLSX_MAX_ROWS: Final = 1_048_576
XLSX_MAX_COLUMNS: Final = 16_384
XLSX_MAX_SHEET_NAME: Final = 31
XLSX_NAME_NAMESPACE: Final = "workbook-name"
XLSX_NAME_PREFIX: Final = "range_"
XLSX_RANGE_PATTERN: Final = (
    r"(?:\$?[A-Z]{1,3}\$?[1-9][0-9]*(?::\$?[A-Z]{1,3}\$?[1-9][0-9]*)?"
    r"|\$?[A-Z]{1,3}:\$?[A-Z]{1,3}|\$?[1-9][0-9]*:\$?[1-9][0-9]*)"
)
XLSX_BUILTIN_NAMES: Final = (
    "_xlnm.Print_Area",
    "_xlnm.Print_Titles",
    "_xlnm._FilterDatabase",
)
XLSX_COMMENTS_PATTERN: Final = r"xl/(?:comments/)?comments?[1-9][0-9]*\.xml"
XLSX_VML_PATTERN: Final = r"xl/drawings/[A-Za-z_]+[1-9][0-9]*\.vml"
XLSX_SHEET_RELATIONSHIPS_PATTERN: Final = (
    r"xl/worksheets/_rels/sheet[1-9][0-9]*\.xml\.rels"
)
OFFICE_RELATIONSHIP_ID_TEMPLATE: Final = "rId{number}"
OFFICE_VML_NAMESPACE: Final = "urn:schemas-microsoft-com:vml"
OFFICE_LEGACY_NAMESPACE: Final = "urn:schemas-microsoft-com:office:office"
OFFICE_EXCEL_NAMESPACE: Final = "urn:schemas-microsoft-com:office:excel"
OFFICE_XML_TEXT_MODE: Final = "text"
ZIP_FIXED_TIMESTAMP: Final = (1980, 1, 1, 0, 0, 0)
NATIVE_ADAPTER_VERSION: Final = "native-v5"
OFFICE_PUBLIC_FONTS: Final = (
    "Angsana New",
    "Sylfaen",
    "Cordia New",
    "Courier",
    "Symbol",
    "Cambria Math",
    "ＭＳ 明朝",
    "ＭＳ ゴシック",
    "",
    "Arial",
    "Calibri",
    "Cambria",
    "Times New Roman",
    "Courier New",
    "Verdana",
    "Tahoma",
    "Aptos",
    "Helvetica",
    "DaunPenh",
    "DokChampa",
    "Estrangelo Edessa",
    "Euphemia",
    "Gautami",
    "Iskoola Pota",
    "Kalinga",
    "Kartika",
    "Latha",
    "MV Boli",
    "Mangal",
    "Microsoft Himalaya",
    "Microsoft Uighur",
    "Microsoft Yi Baiti",
    "Mongolian Baiti",
    "MoolBoran",
    "Nyala",
    "Plantagenet Cherokee",
    "Raavi",
    "Shruti",
    "Tunga",
    "Vrinda",
    "宋体",
    "新細明體",
    "맑은 고딕",
    "ＭＳ Ｐゴシック",
)
OFFICE_STRUCTURAL_VALUES: Final = (
    "Normal",
    "Office",
    "Office Theme",
    "minor",
    "major",
    "gray125",
    "none",
    "phClr",
    "solid",
    "window",
    "windowText",
    "flat",
    "sng",
    "ctr",
    "circle",
    "orthographicFront",
    "threePt",
    "t",
    "visible",
    "hidden",
    "veryHidden",
    "thin",
    "medium",
    "thick",
    "dashed",
    "dotted",
    "double",
    "left",
    "right",
    "center",
    "general",
    "bottom",
    "top",
    "true",
    "false",
    "rgb",
    "theme",
)
# Supported Office XML vocabulary. Unknown extension elements and attributes
# require a surface adapter instead of inheriting numeric or URL exemptions.
OOXML_DRAWING_NAMESPACE: Final = "http://schemas.openxmlformats.org/drawingml/2006/main"
OOXML_OFFICE_RELATIONSHIP_NAMESPACE: Final = (
    "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
)
OOXML_CORE_NAMESPACE: Final = (
    "http://schemas.openxmlformats.org/package/2006/metadata/core-properties"
)
OOXML_EXTENDED_NAMESPACE: Final = (
    "http://schemas.openxmlformats.org/officeDocument/2006/extended-properties"
)
OOXML_DC_NAMESPACE: Final = "http://purl.org/dc/elements/1.1/"
OOXML_DC_TERMS_NAMESPACE: Final = "http://purl.org/dc/terms/"
OOXML_DC_TYPE_NAMESPACE: Final = "http://purl.org/dc/dcmitype/"
XML_SCHEMA_INSTANCE_NAMESPACE: Final = "http://www.w3.org/2001/XMLSchema-instance"
XML_NAMESPACE: Final = "http://www.w3.org/XML/1998/namespace"
XML_SPACE_ATTRIBUTE: Final = f"{{{XML_NAMESPACE}}}space"
XML_TYPE_ATTRIBUTE: Final = f"{{{XML_SCHEMA_INSTANCE_NAMESPACE}}}type"
OOXML_TIMESTAMP_TYPE: Final = "dcterms:W3CDTF"
OOXML_RELATIONSHIP_ID_PATTERN: Final = r"rId[1-9][0-9]*"
OOXML_RELATIONSHIP_REFERENCE: Final = f"{{{OOXML_OFFICE_RELATIONSHIP_NAMESPACE}}}id"
OOXML_VERIFIED_NAMESPACES: Final = (
    OFFICE_VML_NAMESPACE,
    OFFICE_LEGACY_NAMESPACE,
    OFFICE_EXCEL_NAMESPACE,
    XLSX_NAMESPACE,
    OOXML_DRAWING_NAMESPACE,
    OOXML_CONTENT_NAMESPACE,
    OOXML_RELATIONSHIP_NAMESPACE,
    OOXML_OFFICE_RELATIONSHIP_NAMESPACE,
    OOXML_CORE_NAMESPACE,
    OOXML_EXTENDED_NAMESPACE,
    OOXML_DC_NAMESPACE,
    OOXML_DC_TERMS_NAMESPACE,
    OOXML_DC_TYPE_NAMESPACE,
    XML_SCHEMA_INSTANCE_NAMESPACE,
    XML_NAMESPACE,
)
OOXML_NAMESPACE_PREFIX_PATTERN: Final = (
    r"(?:|ns[0-9]+|a|s|x|r|v|o|cp|dc|dcterms|dcmitype|xsi|xml)"
)
OOXML_WORKSHEET_PART_PATTERN: Final = r"xl/worksheets/sheet[1-9][0-9]*\.xml"
OOXML_THEME_PART_PATTERN: Final = r"xl/theme/theme[1-9][0-9]*\.xml"
OOXML_CORE_PART: Final = "docProps/core.xml"
OOXML_EXTENDED_PART: Final = "docProps/app.xml"
OOXML_WORKBOOK_RELATIONSHIPS: Final = "xl/_rels/workbook.xml.rels"
OOXML_SUPPORTED_PARTS: Final = (
    OOXML_CONTENT_TYPES,
    OOXML_PACKAGE_RELATIONSHIPS,
    OOXML_WORKBOOK_RELATIONSHIPS,
    OOXML_CORE_PART,
    OOXML_EXTENDED_PART,
    XLSX_WORKBOOK,
    XLSX_STYLES,
    XLSX_SHARED_STRINGS,
)
OOXML_SUPPORTED_RELATIONSHIP_TYPES: Final = (
    OOXML_OFFICE_DOCUMENT_RELATIONSHIP,
    OOXML_RELATIONSHIP_NAMESPACE + "/metadata/core-properties",
    *(
        OOXML_OFFICE_RELATIONSHIP_NAMESPACE + "/" + name
        for name in (
            "extended-properties",
            "worksheet",
            "styles",
            "theme",
            "sharedStrings",
            "comments",
            "vmlDrawing",
        )
    ),
)
OOXML_SUPPORTED_CONTENT_TYPES: Final = (
    XLSX_MAIN_TYPE,
    "application/xml",
    "application/vnd.openxmlformats-package.relationships+xml",
    "application/vnd.openxmlformats-package.core-properties+xml",
    "application/vnd.openxmlformats-officedocument.extended-properties+xml",
    *(
        "application/vnd.openxmlformats-officedocument.spreadsheetml." + name + "+xml"
        for name in ("worksheet", "styles", "sharedStrings", "comments")
    ),
    "application/vnd.openxmlformats-officedocument.theme+xml",
    "application/vnd.openxmlformats-officedocument.vmlDrawing",
)
OOXML_CONTENT_EXTENSIONS: Final = ("xml", "rels", "vml")
OOXML_WORKSHEET_VOCABULARY: Final = (
    ("worksheet", ()),
    ("sheetPr", ()),
    ("outlinePr", ("summaryBelow", "summaryRight", "showOutlineSymbols")),
    ("pageSetUpPr", ("fitToPage", "autoPageBreaks")),
    ("dimension", ("ref",)),
    ("sheetViews", ()),
    ("sheetView", ("workbookViewId", "showGridLines", "topLeftCell")),
    ("selection", ("activeCell", "activeCellId", "sqref")),
    (
        "sheetFormatPr",
        ("baseColWidth", "defaultRowHeight", "defaultColWidth", "customHeight"),
    ),
    ("cols", ()),
    (
        "col",
        (
            "min",
            "max",
            "width",
            "style",
            "hidden",
            "bestFit",
            "customWidth",
            "outlineLevel",
            "collapsed",
        ),
    ),
    ("sheetData", ()),
    (
        "row",
        (
            "r",
            "s",
            "ht",
            "hidden",
            "customHeight",
            "customFormat",
            "outlineLevel",
            "collapsed",
            "thickTop",
            "thickBot",
        ),
    ),
    ("c", ("r", "s", "t")),
    ("is", ()),
    ("t", (XML_SPACE_ATTRIBUTE,)),
    ("v", ()),
    ("pageMargins", ("left", "right", "top", "bottom", "header", "footer")),
    ("legacyDrawing", (OOXML_RELATIONSHIP_REFERENCE,)),
)
OOXML_COMMENT_VOCABULARY: Final = (
    ("comments", ()),
    ("authors", ()),
    ("author", ()),
    ("commentList", ()),
    ("comment", ("ref", "authorId", "shapeId")),
    ("text", ()),
    ("t", (XML_SPACE_ATTRIBUTE,)),
    ("r", ()),
    ("rPr", ()),
    ("b", ("val",)),
    ("i", ("val",)),
    ("u", ("val",)),
    ("sz", ("val",)),
    ("rFont", ("val",)),
    ("color", ("rgb", "indexed", "theme", "tint", "auto")),
    ("family", ("val",)),
    ("charset", ("val",)),
    ("scheme", ("val",)),
)
OOXML_COMMENT_CHILDREN: Final = (
    ("comments", ("authors", "commentList")),
    ("authors", ("author",)),
    ("author", ()),
    ("commentList", ("comment",)),
    ("comment", ("text",)),
    ("text", ("t", "r")),
    ("r", ("rPr", "t")),
    ("rPr", ("b", "i", "u", "sz", "rFont", "color", "family", "charset", "scheme")),
)
# Only geometry and display controls for legacy comment shapes are supported.
# Embedded pictures, scripts, links, and arbitrary VML attributes are not geometry.
VML_ATTRIBUTE_RULES: Final = (
    ("xml", ()),
    (
        f"{{{OFFICE_LEGACY_NAMESPACE}}}shapelayout",
        ((f"{{{OFFICE_VML_NAMESPACE}}}ext", r"edit"),),
    ),
    (
        f"{{{OFFICE_LEGACY_NAMESPACE}}}idmap",
        ((f"{{{OFFICE_VML_NAMESPACE}}}ext", r"edit"), ("data", r"[0-9, ]+")),
    ),
    (
        f"{{{OFFICE_VML_NAMESPACE}}}shapetype",
        (
            ("id", r"_x[0-9A-Fa-f]{4}_t[0-9]+"),
            ("coordsize", r"[0-9]+,[0-9]+"),
            (f"{{{OFFICE_LEGACY_NAMESPACE}}}spt", r"[0-9]+"),
            ("path", r"[mlcxevqbarnt0-9, .+\-]+"),
        ),
    ),
    (f"{{{OFFICE_VML_NAMESPACE}}}stroke", (("joinstyle", r"miter|round|bevel"),)),
    (
        f"{{{OFFICE_VML_NAMESPACE}}}path",
        (
            ("gradientshapeok", r"t|f|true|false"),
            (f"{{{OFFICE_LEGACY_NAMESPACE}}}connecttype", r"rect|none"),
        ),
    ),
    (
        f"{{{OFFICE_VML_NAMESPACE}}}shape",
        (
            ("id", r"_x[0-9A-Fa-f]{4}_s[0-9]+"),
            ("type", r"#_x[0-9A-Fa-f]{4}_t[0-9]+"),
            ("style", ""),
            ("fillcolor", r"#[0-9A-Fa-f]{6}|yellow|white|black"),
            (f"{{{OFFICE_LEGACY_NAMESPACE}}}insetmode", r"auto|custom"),
        ),
    ),
    (
        f"{{{OFFICE_VML_NAMESPACE}}}fill",
        (("color2", r"#[0-9A-Fa-f]{6}|yellow|white|black"),),
    ),
    (
        f"{{{OFFICE_VML_NAMESPACE}}}shadow",
        (("color", r"#[0-9A-Fa-f]{6}|black|white"), ("obscured", r"t|f|true|false")),
    ),
    (f"{{{OFFICE_VML_NAMESPACE}}}textbox", (("style", ""),)),
    ("div", (("style", ""),)),
    (f"{{{OFFICE_EXCEL_NAMESPACE}}}ClientData", (("ObjectType", r"Note"),)),
    *(
        (f"{{{OFFICE_EXCEL_NAMESPACE}}}{name}", ())
        for name in (
            "MoveWithCells",
            "SizeWithCells",
            "AutoFill",
            "Row",
            "Column",
            "Anchor",
            "Visible",
        )
    ),
)
VML_STYLE_RULES: Final = (
    ("position", r"absolute|relative"),
    ("visibility", r"hidden|visible"),
    ("text-align", r"left|right|center"),
    ("mso-direction-alt", r"auto"),
    *(
        (name, r"-?[0-9]+(?:\.[0-9]+)?(?:pt|px)?")
        for name in (
            "margin-left",
            "margin-top",
            "width",
            "height",
            "z-index",
            "left",
            "top",
        )
    ),
)
OOXML_WORKBOOK_VOCABULARY: Final = (
    ("workbook", ()),
    (
        "workbookPr",
        (
            "date1904",
            "filterPrivacy",
            "showObjects",
            "saveExternalLinkValues",
            "updateLinks",
        ),
    ),
    ("workbookProtection", ()),
    ("bookViews", ()),
    (
        "workbookView",
        (
            "activeTab",
            "autoFilterDateGrouping",
            "firstSheet",
            "minimized",
            "showHorizontalScroll",
            "showSheetTabs",
            "showVerticalScroll",
            "tabRatio",
            "visibility",
            "windowHeight",
            "windowWidth",
            "xWindow",
            "yWindow",
        ),
    ),
    ("sheets", ()),
    ("sheet", ("name", "sheetId", "state", OOXML_RELATIONSHIP_REFERENCE)),
    ("definedNames", ()),
    ("definedName", ("name", "localSheetId", "hidden", "comment", "description")),
    (
        "calcPr",
        (
            "calcId",
            "fullCalcOnLoad",
            "calcMode",
            "forceFullCalc",
            "calcOnSave",
            "iterate",
            "iterateCount",
            "iterateDelta",
            "refMode",
        ),
    ),
)
OOXML_STYLE_VOCABULARY: Final = (
    ("styleSheet", ()),
    ("numFmts", ("count",)),
    ("numFmt", ("numFmtId", "formatCode")),
    ("fonts", ("count",)),
    ("font", ()),
    *(
        (name, ("val",))
        for name in (
            "name",
            "family",
            "sz",
            "scheme",
            "b",
            "i",
            "u",
            "strike",
            "outline",
            "shadow",
            "condense",
            "extend",
            "vertAlign",
            "charset",
        )
    ),
    ("color", ("rgb", "indexed", "theme", "tint", "auto")),
    ("fills", ("count",)),
    ("fill", ()),
    ("patternFill", ("patternType",)),
    ("fgColor", ("rgb", "indexed", "theme", "tint", "auto")),
    ("bgColor", ("rgb", "indexed", "theme", "tint", "auto")),
    ("borders", ("count",)),
    ("border", ("diagonalUp", "diagonalDown", "outline")),
    *(
        (name, ("style",))
        for name in (
            "left",
            "right",
            "top",
            "bottom",
            "diagonal",
            "vertical",
            "horizontal",
            "start",
            "end",
        )
    ),
    ("cellStyleXfs", ("count",)),
    ("cellXfs", ("count",)),
    (
        "xf",
        (
            "borderId",
            "fillId",
            "fontId",
            "numFmtId",
            "pivotButton",
            "quotePrefix",
            "xfId",
            "applyAlignment",
            "applyBorder",
            "applyFill",
            "applyFont",
            "applyNumberFormat",
            "applyProtection",
        ),
    ),
    (
        "alignment",
        (
            "horizontal",
            "vertical",
            "textRotation",
            "wrapText",
            "shrinkToFit",
            "indent",
            "relativeIndent",
            "justifyLastLine",
            "readingOrder",
        ),
    ),
    ("protection", ("locked", "hidden")),
    ("cellStyles", ("count",)),
    ("cellStyle", ("name", "xfId", "builtinId", "hidden", "customBuiltin")),
    ("dxfs", ("count",)),
    ("dxf", ()),
    ("tableStyles", ("count", "defaultTableStyle", "defaultPivotStyle")),
    ("colors", ()),
    ("indexedColors", ()),
    ("rgbColor", ("rgb",)),
)
OOXML_THEME_VOCABULARY: Final = (
    ("theme", ("name",)),
    ("themeElements", ()),
    *((name, ("name",)) for name in ("clrScheme", "fontScheme", "fmtScheme")),
    *(
        (name, ())
        for name in (
            "dk1",
            "lt1",
            "dk2",
            "lt2",
            "accent1",
            "accent2",
            "accent3",
            "accent4",
            "accent5",
            "accent6",
            "hlink",
            "folHlink",
            "majorFont",
            "minorFont",
            "fillStyleLst",
            "solidFill",
            "gsLst",
            "lnStyleLst",
            "effectStyleLst",
            "effectStyle",
            "effectLst",
            "scene3d",
            "sp3d",
            "bgFillStyleLst",
            "objectDefaults",
            "extraClrSchemeLst",
        )
    ),
    ("sysClr", ("val", "lastClr")),
    ("srgbClr", ("val",)),
    ("schemeClr", ("val",)),
    *(
        (name, ("typeface", "panose", "pitchFamily", "charset"))
        for name in ("latin", "ea", "cs")
    ),
    ("font", ("script", "typeface")),
    ("gradFill", ("rotWithShape", "flip")),
    ("gs", ("pos",)),
    *(
        (name, ("val",))
        for name in (
            "tint",
            "shade",
            "alpha",
            "alphaMod",
            "alphaOff",
            "sat",
            "satMod",
            "satOff",
            "lum",
            "lumMod",
            "lumOff",
            "hue",
            "hueMod",
            "hueOff",
        )
    ),
    ("lin", ("ang", "scaled")),
    ("ln", ("algn", "cap", "cmpd", "w")),
    ("prstDash", ("val",)),
    (
        "outerShdw",
        ("blurRad", "dir", "dist", "rotWithShape", "algn", "sx", "sy", "kx", "ky"),
    ),
    ("camera", ("prst", "fov", "zoom")),
    ("rot", ("lat", "lon", "rev")),
    ("lightRig", ("dir", "rig")),
    ("bevelT", ("h", "w", "prst")),
    ("bevelB", ("h", "w", "prst")),
    ("path", ("path",)),
    ("fillToRect", ("b", "l", "r", "t")),
)
OOXML_CORE_VOCABULARY: Final = (
    (
        OOXML_CORE_NAMESPACE,
        (
            "coreProperties",
            "category",
            "contentStatus",
            "contentType",
            "keywords",
            "lastModifiedBy",
            "lastPrinted",
            "revision",
            "version",
        ),
    ),
    (
        OOXML_DC_NAMESPACE,
        ("title", "subject", "creator", "description", "identifier", "language"),
    ),
    (OOXML_DC_TERMS_NAMESPACE, ("created", "modified")),
)
OOXML_EXTENDED_VOCABULARY: Final = (
    "Properties",
    "Template",
    "Manager",
    "Company",
    "Pages",
    "Words",
    "Characters",
    "PresentationFormat",
    "Lines",
    "Paragraphs",
    "Slides",
    "Notes",
    "TotalTime",
    "HiddenSlides",
    "MMClips",
    "ScaleCrop",
    "LinksUpToDate",
    "CharactersWithSpaces",
    "SharedDoc",
    "HyperlinkBase",
    "HyperlinksChanged",
    "Application",
    "AppVersion",
    "DocSecurity",
)
MRN_NAMESPACE: Final = "mrn"
PATIENT_ID_NAMESPACE: Final = "patient-id"
ENCOUNTER_ID_NAMESPACE: Final = "encounter-id"
ACCOUNT_NAMESPACE: Final = "account-number"
RELATIVE_NAME_NAMESPACE: Final = "relative-name"
IDENTITY_PATIENT: Final = "patient"
IDENTITY_RELATIVE: Final = "relative"
ROW_CONTEXT_TEMPLATE: Final = "{input_sha256}:row:{number}:{role}"
TABULAR_FIELD_ALIASES: Final = (
    (FIELD_CLINICAL, "version", ("schema", "schema_version", "version")),
    (
        FIELD_ORGANIZATION,
        "organization",
        (
            "payer",
            "insurer",
            "insurance",
            "insurance_company",
            "plan",
            "organization",
            "institution",
        ),
    ),
    (
        FIELD_CLINICAL,
        LAB_DESCRIPTION_NAMESPACE,
        ("test", "test_name", "laboratory_test"),
    ),
    (FIELD_CLINICAL, "application", ("application",)),
    (FIELD_CLINICAL, "version", ("appversion",)),
    (FIELD_IDENTIFIER, "claim", ("claim_no", "claim_id")),
    (FIELD_IDENTIFIER, "member", ("member_id", "member_number", "subscriber_id")),
    (FIELD_IDENTIFIER, "ssn", ("ssn", "social_security_number")),
    (
        FIELD_PROVIDER_NAME,
        "",
        ("pcp", "verified_by", "creator", "last_modified_by", "author"),
    ),
    (FIELD_PROVIDER_ID, NPI_NAMESPACE, ("pcp_npi",)),
    (FIELD_DATE, "", ("dos", "collected", "verified_on", "created", "modified")),
    (FIELD_LOCATION, "", ("city", "county", "district")),
    (FIELD_CLINICAL, "state", ("state",)),
    (FIELD_CLINICAL, "quantity", ("charge_usd", "amount")),
    (FIELD_CLINICAL, "icd", ("primary_dx",)),
    (FIELD_PATIENT_NAME, "", ("patient", "patient_name", "patient_full_name")),
    (
        FIELD_PROVIDER_NAME,
        "",
        ("attending", "attending_name", "provider_name", "physician"),
    ),
    (
        FIELD_PATIENT_ID,
        MRN_NAMESPACE,
        ("mrn", "medical_record_number", "medical_record_no"),
    ),
    (FIELD_PATIENT_ID, PATIENT_ID_NAMESPACE, ("patient_id", "patient_identifier")),
    (FIELD_PROVIDER_ID, NPI_NAMESPACE, ("npi", "attending_npi", "provider_npi")),
    (FIELD_IDENTIFIER, ENCOUNTER_ID_NAMESPACE, ("encounter_id", "visit_id")),
    (FIELD_IDENTIFIER, ACCOUNT_NAMESPACE, ("account", "account_number", "account_no")),
    (FIELD_BIRTH_DATE, "", ("birth_date", "date_of_birth", "dob")),
    (
        FIELD_DATE,
        "",
        (
            "admit_ts",
            "discharge_ts",
            "admit_date",
            "discharge_date",
            "admission_date",
            "encounter_date",
            "event_date",
            "collection_date",
            "date",
        ),
    ),
    (FIELD_AGE, "", ("age", "age_years")),
    (
        FIELD_PHONE,
        PHONE_NAMESPACE,
        ("contact", "phone", "phone_number", "telephone", "mobile", "fax"),
    ),
    (FIELD_EMAIL, EMAIL_NAMESPACE, ("email", "email_address")),
    (FIELD_NETWORK, "", ("ip", "ip_address", "ipv4", "ipv6")),
    (FIELD_WEB, "", ("url", "web_address", "website", "portal_url")),
    (FIELD_ADDRESS, ADDRESS_NAMESPACE, ("address", "street_address", "street")),
    (FIELD_ZIP, "", ("zip", "zip_code", "zipcode", "postal_code")),
    (
        FIELD_LOT,
        PRODUCT_LOT_NAMESPACE,
        ("lot_no", "lot_number", "device_serial_number", "device_serial", "udi"),
    ),
    (
        FIELD_CLINICAL,
        "icd",
        ("dx_codes", "dx_code", "diagnosis_codes", "diagnosis_code", "icd10", "icd_10"),
    ),
    (FIELD_CLINICAL, "procedure", ("cpt_codes", "cpt_code", "cpt", "hcpcs")),
    (FIELD_CLINICAL, "loinc", ("loinc", "loinc_code")),
    (FIELD_CLINICAL, "ndc", ("ndc", "ndc_code")),
    (FIELD_CLINICAL, "rxnorm", ("rxnorm", "rxnorm_code")),
    (FIELD_CLINICAL, "quantity", ("lab_value", "lab_result", "result_value", "value")),
    (FIELD_CLINICAL, "sex", ("sex", "gender")),
    (FIELD_CLINICAL, "unit", ("unit", "units")),
)
CLINICAL_FIELD_PATTERNS: Final = (
    (
        "kinship",
        r"(?:ASC|BRO|CGV|CHD|DEP|DOM|EMC|EME|EXF|FCH|FND|FTH|GCH|GRD|GRP|MTH|NCH|NON|OAD|OTH|OWN|PAR|SCH|SEL|SIB|SIS|SPO|TRA|UNK|WRD|DAU|SON)",
    ),
    (
        "application",
        (
            r"(?:Microsoft (?:Excel|(?:Macintosh )?Word)|"
            r"Microsoft Excel Compatible / Openpyxl [0-9.]+)"
        ),
    ),
    ("version", r"v?[0-9]+(?:\.[0-9]+)*"),
    ("state", r"[A-Z]{2}"),
    ("icd", r"[A-Z][0-9][0-9A-Z](?:\.[0-9A-Z]{1,4})?"),
    ("procedure", r"(?:[0-9]{5}|[A-Z][0-9]{4}|[0-9]{4}[A-Z])"),
    ("loinc", r"[0-9]{1,7}-[0-9]"),
    ("ndc", r"(?:[0-9]{10,11}|[0-9]{4,5}-[0-9]{3,4}-[0-9]{1,2})"),
    ("rxnorm", r"[0-9]+"),
    ("quantity", r"[<>≤≥]?[+-]?[0-9]+(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?"),
    ("sex", r"(?:M|F|O|U|male|female|other|unknown)"),
)
# Supported medical symbols from UCUM 2.2: https://ucum.org/ucum.
# Copyright 1999-2024 Regenstrief Institute, Inc.; https://ucum.org/license.
# This vocabulary is a validation subset, not a modified unit standard.
CLINICAL_UNIT_MAX_LENGTH: Final = 128
CLINICAL_UNIT_PREFIXES: Final = tuple(
    "Y Z E P T G M k h da d c m u n p f a z y".split()
)
CLINICAL_UNIT_METRIC_ATOMS: Final = tuple(
    "m s g rad K C cd mol sr Hz N Pa J W A V F Ohm S Wb Cel T H lm lx "
    "Bq Gy Sv l L ar t bar u eV pc gf Gal dyn erg P St G Ci R RAD REM "
    "cal cal_IT cal_th tex m[H2O] m[Hg] eq osm kat U [iU] [IU] Np B "
    "bit By Bd".split()
)
CLINICAL_UNIT_ATOMS: Final = tuple(
    "10* 10^ % [ppm] [ppb] deg min h d a wk mo atm [lb_av] [oz_av] "
    "[in_i] [ft_i] [degF] [degR] [Cal] [HPF] [LPF] [CFU] [PFU] "
    "[pH] [arb'U] [USP'U] [IU]".split()
)
CLINICAL_UNIT_ALIASES: Final = (("mmHg", "mm[Hg]"), ("mcg", "ug"))
CLINICAL_CODE_SEPARATOR_PATTERN: Final = r"[;,|\s]+"
AGE_EXPLICIT_PATTERN: Final = (
    r"(?i)\bage\s*[:=]?\s*(?P<age>[0-9]{1,3})(?:\+)?\b"
    r"(?!\s*(?:days?|weeks?|months?)\b)"
)
AGE_WORD_PATTERN: Final = (
    r"(?i)\b(?P<age>ninety(?:[- ](?:one|two|three|four|five|six|seven|eight|nine))?"
    r"|(?:one[- ])?hundred(?:[- ](?:and[- ])?(?:[a-z]+(?:[- ][a-z]+)?))?)"
    r"(?:[- ]years?[- ]old|\s+years?\s+of\s+age)\b"
)
MONTH_NAMES: Final = (
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
)
DATE_NAMED_MDY_PATTERN: Final = (
    r"(?P<month_name>[A-Za-z]+)(?P<separator> )(?P<day>[0-9]{1,2})"
    r"(?P<year_separator>,? )(?P<year>[0-9]{4})(?P<clock>.*)"
)
DATE_NAMED_DMY_PATTERN: Final = (
    r"(?P<day>[0-9]{1,2})(?P<separator>[- ])(?P<month_name>[A-Za-z]+)"
    r"(?P=separator)(?P<year>[0-9]{4})(?P<clock>.*)"
)
TEXT_NAMED_DATE_PATTERN: Final = (
    r"(?i)\b(?:[0-9]{1,2}[- ](?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|"
    r"Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|"
    r"Dec(?:ember)?)[- ][0-9]{4}"
    r"|(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|"
    r"Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?) "
    r"[0-9]{1,2},? [0-9]{4})\b"
)

# Free-text evidence. These are field-independent clinical and PHI patterns.
TEXT_EMAIL_PATTERN: Final = r"(?<![\w.+-])[\w.+-]+@[\w-]+(?:\.[\w-]+)+(?![\w-])"
TEXT_PHONE_PATTERN: Final = (
    r"(?<![\w+])(?:(?:\+|00)[1-9](?:[ \t().-]*[0-9]){6,14}"
    r"|(?:\+?1[ .-]?)?(?:\([2-9][0-9]{2}\)|[2-9][0-9]{2})"
    r"[ .-]?[0-9]{3}[ .-]?[0-9]{4})"
    r"(?:[ \t]*(?i:ext(?:ension)?\.?|x|#)[ \t]*[:=]?[ \t]*[0-9]+)?"
    r"(?![\w]|[ \t().-]*[0-9])"
)
TEXT_STREET_PATTERN: Final = (
    r"(?i)\b[0-9]{1,6}\s+(?:[\w.'’\-]+\s+){1,6}"
    r"(?:avenue|ave|street|st|road|rd|lane|ln|drive|dr|boulevard|blvd|court|ct|way)"
    r"\b\.?"
)
TEXT_RELATIVE_PATTERN: Final = (
    r"(?i:\b(?:spouse|wife|husband|daughter|son|mother|father|sister|brother|partner|"
    r"caregiver|guardian|next of kin))\s+"
    r"(?P<name>[A-ZÀ-ÖØ-Þ][\w'’\-]*(?:\s+[A-ZÀ-ÖØ-Þ][\w'’\-]*){0,3})"
)
TEXT_PROVIDER_PATTERN: Final = (
    r"(?i:\b(?:Dr\.?|Doctor|Prof\.?))\s+"
    r"(?P<name>[A-ZÀ-ÖØ-Þ][\w'’\-]*(?:\s+[A-ZÀ-ÖØ-Þ][\w'’\-]*){0,3})"
)
AGE_YEARS_PATTERN: Final = (
    r"(?i)\b(?P<age>[0-9]{1,3})(?:\+)?(?:[- ]years?[- ]old|\s*y/o)\b"
)
TEXT_MASK_TOKEN: Final = " [REDACTED] "
# Clinical code validation. A valid checksum does not establish terminology membership.
SNOMED_LABELLED_CODE_PATTERN: Final = (
    r"(?i)\bSNOMED(?:[ \t]+CT)?(?:[ \t]*[:#][ \t]*|[ \t]+)"
    r"(?P<code>[0-9]+)(?![\w+\-]|\.[0-9])"
)
SNOMED_CONCEPT_ID_PATTERN: Final = r"[1-9][0-9]{5,17}"
SNOMED_CONCEPT_PARTITIONS: Final = ("00", "10")
SNOMED_EXTENSION_PARTITION: Final = "10"
SNOMED_EXTENSION_MINIMUM_DIGITS: Final = 11
VERHOEFF_MULTIPLICATION: Final = (
    (0, 1, 2, 3, 4, 5, 6, 7, 8, 9),
    (1, 2, 3, 4, 0, 6, 7, 8, 9, 5),
    (2, 3, 4, 0, 1, 7, 8, 9, 5, 6),
    (3, 4, 0, 1, 2, 8, 9, 5, 6, 7),
    (4, 0, 1, 2, 3, 9, 5, 6, 7, 8),
    (5, 9, 8, 7, 6, 0, 4, 3, 2, 1),
    (6, 5, 9, 8, 7, 1, 0, 4, 3, 2),
    (7, 6, 5, 9, 8, 2, 1, 0, 4, 3),
    (8, 7, 6, 5, 9, 3, 2, 1, 0, 4),
    (9, 8, 7, 6, 5, 4, 3, 2, 1, 0),
)
VERHOEFF_PERMUTATIONS: Final = (
    (0, 1, 2, 3, 4, 5, 6, 7, 8, 9),
    (1, 5, 7, 6, 2, 8, 3, 0, 9, 4),
    (5, 8, 0, 3, 7, 9, 6, 1, 4, 2),
    (8, 9, 1, 6, 0, 4, 3, 5, 2, 7),
    (9, 4, 5, 3, 1, 2, 6, 8, 7, 0),
    (4, 2, 8, 6, 5, 7, 3, 9, 0, 1),
    (2, 7, 9, 3, 8, 0, 6, 4, 1, 5),
    (7, 0, 4, 6, 9, 1, 3, 2, 5, 8),
)
TEXT_CLINICAL_PATTERNS: Final = (
    r"(?i)\b(?:spoke|discussed|reviewed)\s+w/",
    r"(?im)^(?:progress note|discharge summary|referral (?:letter|packet)|"
    r"clinical note|history of present illness|assessment and plan)\s*$",
    r"(?i)\b(?:sex|gender)\s*[:=]\s*(?:M|F|O|U|male|female|other|unknown)\b",
    r"(?i)\b(?:in|since|during|through|year|quit|dx|diagnosed)\s+(?:19|20)[0-9]{2}\b",
    r"(?i)\b(?:T|temp(?:erature)?)\s*[:=]?\s*[0-9]+(?:\.[0-9]+)?\s*°?[CF]\b",
    r"(?i)\b(?:A1c|HbA1c|GCS|LDL|HDL|HR|BP|pulse|heart rate|blood pressure)\s*[:=]?\s*"
    r"[0-9]+(?:\.[0-9]+)?(?:/[0-9]+)?\s*(?:%|mg/dL|mmol/L|mmHg|bpm)?",
    r"\b(?:MRN|DOB|NPI|SSN)(?=[ :\t])",
    r"\b(?:MD|RN)\b",
    r"(?i)\b(?:renal|diabetic|cardiac|low[- ]sodium|low[- ]fat|clear[- ]liquid)"
    r"\s+diet\b",
    r"\b[A-Z][0-9][0-9A-Z](?:\.[A-Z0-9]{1,4})?\b",
    r"(?i)\b(?:LOINC|CPT|HCPCS|RxNorm|NDC|ICD[- ]?10)\s*[:#]?\s*[A-Z0-9.\-]+\b",
    r"(?i)\b[a-z][\w-]*\s+[0-9]+(?:[./][0-9]+)?\s*(?:mg|mcg|µg|g|mL|units?|mmol|mEq|puffs?)\b",
    r"(?i)\b[a-z][\w-]*\s+[0-9]+/[0-9]+\s*(?:BID|TID|QID)\b",
    r"(?i)\b[0-9]+(?:\.[0-9]+)?\s*(?:mg/dL|mmol/L|mg|mcg|g|mL|units?|%|days?|weeks?|months?|years?)\b",
    r"\b[\w'’\-]+(?:'s|’s)?\s+(?i:disease|syndrome|palsy|sign|contracture|lymphoma)\b",
    r"(?i)\b(?:BID|TID|QID|PRN|qHS|PO|IV|IM|MDI|GCS|LDL|HDL|A1c|HbA1c|HR|BP|HTN|Neuro|Cardio|daily|weekly|monthly|yearly)\b",
)
PRESERVED_US_GEOGRAPHY: Final = (
    "usa",
    "us",
    "united states",
    "united states of america",
    "alabama",
    "alaska",
    "arizona",
    "arkansas",
    "california",
    "colorado",
    "connecticut",
    "delaware",
    "florida",
    "georgia",
    "hawaii",
    "idaho",
    "illinois",
    "indiana",
    "iowa",
    "kansas",
    "kentucky",
    "louisiana",
    "maine",
    "maryland",
    "massachusetts",
    "michigan",
    "minnesota",
    "mississippi",
    "missouri",
    "montana",
    "nebraska",
    "nevada",
    "new hampshire",
    "new jersey",
    "new mexico",
    "new york",
    "north carolina",
    "north dakota",
    "ohio",
    "oklahoma",
    "oregon",
    "pennsylvania",
    "rhode island",
    "south carolina",
    "south dakota",
    "tennessee",
    "texas",
    "utah",
    "vermont",
    "virginia",
    "washington",
    "west virginia",
    "wisconsin",
    "wyoming",
    "district of columbia",
    "puerto rico",
)

# Calendar-date spelling and older-age generalization
DATE_OFFSET_NAMESPACE: Final = "patient-date-offset"
DATE_STYLE_YMD: Final = "ymd"
DATE_STYLE_MDY: Final = "mdy"
DATE_STYLE_COMPACT: Final = "compact"
DATE_STYLE_NAMED_MDY: Final = "named_mdy"
DATE_STYLE_NAMED_DMY: Final = "named_dmy"
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
    r"(?P<year>[0-9]{4}|[0-9]{2})" + DATE_CLOCK_PATTERN
)
DATE_SHORT_YEAR_PIVOT: Final = 69
DATE_SHORT_YEAR_BASE: Final = 2000
DATE_CENTURY_YEARS: Final = 100
TEXT_DATE_PATTERN: Final = (
    r"(?<![\w/])(?:[0-9]{4}[-/][0-9]{1,2}[-/][0-9]{1,2}"
    r"|[0-9]{1,2}/[0-9]{1,2}/(?:[0-9]{4}|[0-9]{2}))" + DATE_CLOCK_PATTERN + r"(?![\w/])"
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


# Labelled native text fields. Delimiters remain outside the sensitive value.
TEXT_PART: Final = "body"
TEXT_LABEL_FIELDS: Final = (
    (
        r"(?im)\bPatient:[ \t]*(?P<value>[^\r\n]+?)(?=[ \t]{2,}|[|]|\r?$)",
        "patient_name",
        "",
    ),
    (
        r"(?im)\bAttending:[ \t]*(?P<value>[^\r\n]+?)"
        r"(?=,[ \t]*MD\b|[ \t]*\(NPI|[ \t]{2,}|\r?$)",
        "provider_name",
        "",
    ),
    (r"(?im)\bDOB:[ \t]*(?P<value>[^\r\n]+?)(?=[ \t]{2,}|[|]|\r?$)", "birth_date", ""),
    (r"(?im)\bMRN:[ \t]*(?P<value>[A-Za-z0-9-]+)", "patient_id", "mrn"),
    (r"(?im)\bNPI[ :\t]+(?P<value>[0-9]{10})\b", "provider_id", "npi"),
    (
        r"(?im)\b(?:Admit(?:ted)?|Discharge(?:d)?):[ \t]*(?P<value>[^\r\n]+?)"
        r"(?=[ \t]{2,}|[|]|\r?$)",
        "date",
        "",
    ),
)
TEXT_IDENTIFIER_PATTERNS: Final = (
    (r"(?i)\bMRN[ :#]+(?P<value>[A-Z0-9]+(?:-[A-Z0-9]+)*)", "mrn"),
    (
        r"(?i)\b(?:account|room|visit|serial|license)"
        r"(?:[ \t]*[:#][ \t]*|[ \t]+(?=[A-Z0-9-]*[0-9]))"
        r"(?P<value>[A-Z0-9]+(?:-[A-Z0-9]+)*)",
        "identifier",
    ),
    (r"(?<![0-9])(?P<value>[0-9]{3}-[0-9]{2}-[0-9]{4})(?![0-9])", SSN_NAMESPACE),
)
TEXT_IPV4_PATTERN: Final = r"(?<![\w.])(?:[0-9]{1,3}\.){3}[0-9]{1,3}(?!\w|\.[0-9])"
TEXT_URL_PATTERN: Final = r"https?://[^\s<>\"']+"
TEXT_ZIP_PATTERN: Final = r"\b[A-Z]{2}[ \t]+(?P<value>[0-9]{5}(?:-[0-9]{4})?)\b"
NETWORK_NAMESPACE: Final = "network-address"
WEB_NAMESPACE: Final = "web-address"
SSN_DIGITS: Final = 9
SSN_AREA_LIMIT: Final = 899
SSN_DISALLOWED_AREA: Final = 666
SURROGATE_WEB_TEMPLATE: Final = "https://example.invalid/{identifier}"

FIELD_SSN: Final = "ssn"

TEXT_DOCUMENT_HEADER_PATTERN: Final = (
    r"(?i)^(?:patient|attending|DOB|MRN|admit(?:ted)?):"
)


# Supported HL7 ADT fields use one-based standard field positions.
HL7_SEGMENT_ENDINGS: Final = r"(\r\n|\r|\n)"
HL7_ESCAPE_CODES: Final = ("F", "S", "R", "E", "T")
HL7_NAME_MODE: Final = "name"
HL7_PHONE_MODE: Final = "phone"
HL7_VALUE_MODE: Final = "value"
FIELD_RELATIVE_NAME: Final = "relative_name"
FIELD_PERSON_NAME: Final = "person_name"
UNLINKED_PERSON_NAMESPACE: Final = "unlinked-person"
HL7_STRUCTURAL_FIELDS: Final = (
    ("MSH", 9, r"ADT{component}A[0-9]{2}(?:{component}ADT_A[0-9]{2})?"),
    ("MSH", 11, r"[PTD]"),
    ("MSH", 12, r"2\.[3456789](?:\.[0-9]+)?"),
    ("MSH", 18, r"UNICODE UTF-8|ASCII|8859/1"),
    ("EVN", 1, r"A[0-9]{2}"),
    ("PID", 1, r"[0-9]+"),
    ("PID", 8, r"[MFOUA]"),
    ("NK1", 1, r"[0-9]+"),
    ("PV1", 1, r"[0-9]+"),
    ("PV1", 2, r"[BEIOPRNU]"),
    ("DG1", 1, r"[0-9]+"),
    ("DG1", 6, r"[AFW]"),
    ("OBX", 1, r"[0-9]+"),
    ("OBX", 2, r"NM|TX|ST|FT"),
    ("OBX", 7, r"[0-9.<>=+\-]+"),
    ("OBX", 8, r"[HLAN]{1,2}"),
    ("OBX", 11, r"[CFIPRXSUWD]"),
    ("NTE", 1, r"[0-9]+"),
    ("NTE", 2, r"[LOP]"),
)
HL7_DATE_FIELDS: Final = (
    ("MSH", 7),
    ("EVN", 2),
    ("EVN", 6),
    ("PID", 7),
    ("PID", 29),
    ("PV1", 44),
    ("PV1", 45),
    ("DG1", 5),
    ("OBX", 14),
)
HL7_IDENTIFIER_FIELDS: Final = (
    ("MSH", 3),
    ("MSH", 4),
    ("MSH", 5),
    ("MSH", 6),
    ("MSH", 10),
    ("PV1", 19),
)
HL7_ADDRESS_FIELDS: Final = (("PID", 11), ("NK1", 4))
HL7_PHONE_FIELDS: Final = (("PID", 13), ("PID", 14), ("NK1", 5), ("NK1", 6))
KINSHIP_DISPLAY_NAMESPACE: Final = "kinship-display:"
# HL7 THO v2-0063, version 3.0.0 (CC0), with explicit DAU/SON local aliases.
# https://terminology.hl7.org/CodeSystem-v2-0063.json
HL7_RELATIONSHIP_DISPLAYS: Final = (
    ("SEL", "Self"),
    ("SPO", "Spouse"),
    ("DOM", "Life partner"),
    ("CHD", "Child"),
    ("GCH", "Grandchild"),
    ("NCH", "Natural child"),
    ("SCH", "Stepchild"),
    ("FCH", "Foster child"),
    ("DEP", "Handicapped dependent"),
    ("WRD", "Ward of court"),
    ("PAR", "Parent"),
    ("MTH", "Mother"),
    ("FTH", "Father"),
    ("CGV", "Care giver"),
    ("GRD", "Guardian"),
    ("GRP", "Grandparent"),
    ("EXF", "Extended family"),
    ("SIB", "Sibling"),
    ("BRO", "Brother"),
    ("SIS", "Sister"),
    ("FND", "Friend"),
    ("OAD", "Other adult"),
    ("EME", "Employee"),
    ("EMR", "Employer"),
    ("ASC", "Associate"),
    ("EMC", "Emergency contact"),
    ("OWN", "Owner"),
    ("TRA", "Trainer"),
    ("MGR", "Manager"),
    ("NON", "None"),
    ("UNK", "Unknown"),
    ("OTH", "Other"),
    ("DAU", "Daughter"),
    ("SON", "Son"),
)


# Conservative vocabulary for coded laboratory display names, not patient text.
LAB_DESCRIPTION_TERMS: Final = (
    "a1c",
    "hb",
    "hba1c",
    "hemoglobin",
    "haemoglobin",
    "hematocrit",
    "haematocrit",
    "glucose",
    "creatinine",
    "urea",
    "nitrogen",
    "sodium",
    "potassium",
    "chloride",
    "bicarbonate",
    "calcium",
    "magnesium",
    "phosphate",
    "albumin",
    "protein",
    "bilirubin",
    "alkaline",
    "phosphatase",
    "aminotransferase",
    "aspartate",
    "alanine",
    "cholesterol",
    "triglycerides",
    "ldl",
    "hdl",
    "wbc",
    "rbc",
    "platelets",
    "leukocytes",
    "erythrocytes",
    "neutrophils",
    "lymphocytes",
    "monocytes",
    "eosinophils",
    "basophils",
    "blood",
    "serum",
    "plasma",
    "urine",
    "whole",
    "mass",
    "volume",
    "moles",
    "substance",
    "number",
    "count",
    "fraction",
    "ratio",
    "total",
    "concentration",
    "in",
    "of",
    "or",
    "and",
    "to",
    "by",
    "automated",
    "manual",
    "estimated",
    "glomerular",
    "filtration",
    "rate",
)

# Model evaluation: fixed synthetic evidence, never production data or secrets.
EVALUATION_TEXT_CORPUS: Final = "benchmarks/corpus/text.json"
EVALUATION_FINDING_TYPES: Final = (
    (FIELD_PATIENT_NAME, "person"),
    (FIELD_PROVIDER_NAME, "person"),
    (FIELD_PERSON_NAME, "person"),
    (FIELD_ORGANIZATION, "organization"),
    (FIELD_LOCATION, "location"),
    (IDENTITY_RELATIVE, "person"),
    (FIELD_DATE, "date"),
    (FIELD_AGE, "age"),
    (FIELD_EMAIL, "contact"),
    (FIELD_PHONE, "contact"),
    (FIELD_NETWORK, "contact"),
    (FIELD_WEB, "contact"),
    (FIELD_SSN, "identifier"),
    (FIELD_IDENTIFIER, "identifier"),
    (FIELD_ADDRESS, "location"),
    (FIELD_ZIP, "location"),
)
# Local CPU model exports and inference contracts
ONNX_THREADS: Final = 1
ONNX_CPU_PROVIDER: Final = "CPUExecutionProvider"
ONNX_INTEGER_TYPE: Final = "tensor(int64)"
ONNX_FLOAT_TYPE: Final = "tensor(float)"
TOKENIZER_FILENAME: Final = "tokenizer.json"
OCR_TIMEOUT_SECONDS: Final = 30
OCR_MAXIMUM_REGIONS: Final = 256
OCR_MAXIMUM_REGION_CHARACTERS: Final = 16384
OCR_MAXIMUM_RESPONSE_BYTES: Final = 2 * 1024 * 1024
OCR_MAXIMUM_ASPECT_RATIO: Final = 64
OCR_IMAGE_FORMATS: Final = ("PNG", "JPEG", "TIFF", "BMP", "WEBP")
OCR_PNG_FORMAT: Final = "PNG"
OCR_TESSDATA_DIRECTORY: Final = "tessdata"
OCR_PPOCR_DIRECTORY: Final = "ppocr-v5"
OCR_ENGLISH_LANGUAGES: Final = ("en", "eng")
TESSERACT_LANGUAGE: Final = "eng"
TESSERACT_TRAINED_DATA: Final = "eng.traineddata"
TESSERACT_OUTPUT_NAME: Final = "recognized"
TESSERACT_OUTPUT_SUFFIX: Final = ".tsv"
TESSERACT_WORD_LEVEL: Final = "5"
TESSERACT_LAYOUT_LEVELS: Final = ("1", "2", "3", "4")
TESSERACT_MAXIMUM_CONFIDENCE: Final = 100
TESSERACT_TSV_FIELDS: Final = (
    "level",
    "page_num",
    "block_num",
    "par_num",
    "line_num",
    "word_num",
    "left",
    "top",
    "width",
    "height",
    "conf",
    "text",
)
PPOCR_CHARACTER_METADATA: Final = "character"
PPOCR_ENGLISH_LANGUAGE: Final = "en"
PPOCR_DETECTOR: Final = "ch_PP-OCRv5_det_mobile.onnx"
PPOCR_CLASSIFIER: Final = "ch_PP-LCNet_x0_25_textline_ori_cls_mobile.onnx"
PPOCR_RECOGNIZERS: Final = (
    (PPOCR_ENGLISH_LANGUAGE, "en_PP-OCRv5_rec_mobile.onnx"),
    ("latin", "latin_PP-OCRv5_rec_mobile.onnx"),
)
GLINER_CONFIG: Final = "gliner_config.json"
GLINER_WEIGHTS: Final = "onnx/model_quint8.onnx"
GLINER_MAXIMUM_TOKENS: Final = 2048
GLINER_MAXIMUM_CANDIDATES: Final = 16384
GLINER_LOGIT_BOUND: Final = 80
GLINER_INPUT_NAMES: Final = (
    "input_ids",
    "attention_mask",
    "words_mask",
    "text_lengths",
)
GLINER_THRESHOLD: Final = 0.3
GLINER_WORD_PATTERN: Final = r"\w+(?:[-_]\w+)*|\S"
GLINER_LABELS: Final = (
    ("name", "person"),
    ("organization medical facility", "organization"),
    ("location address", "location"),
    ("location city", "location"),
    ("location zip", "location"),
    ("date", "date"),
    ("time", "time"),
    ("age", "age"),
    ("email address", "contact"),
    ("phone number", "contact"),
    ("ip address", "contact"),
    ("url", "contact"),
    ("medical record number", "identifier"),
    ("account number", "identifier"),
    ("ssn", "identifier"),
    ("device identifier", "identifier"),
    ("driver license", "identifier"),
)
# Reject only model predictions whose named datatype has no possible syntax.
# These are language/format rules, never document titles or fixture vocabulary.
NER_PHONE_LABEL: Final = "phone number"
NER_EMAIL_LABEL: Final = "email address"
NER_IP_LABEL: Final = "ip address"
NER_URL_LABEL: Final = "url"
NER_ZIP_LABEL: Final = "location zip"
NER_NUMERIC_IDENTIFIER_LABELS: Final = ("ssn", "driver license")
NON_IDENTIFYING_LOCATION_PATTERN: Final = (
    r"(?i)\b(?:(?:drive|driven|return|returned|discharge|discharged|go|going|went|"
    r"walk|walked|at|back|to|from)\s+)?(?:home|here|there|nearby)\b"
)
NON_IDENTIFYING_ROLE_PATTERN: Final = (
    rf"(?i){VERIFIER_ROLE_CONNECTOR}{VERIFIER_MENTION_ROLE}"
)
NER_OLDER_AGE_WORD_PATTERN: Final = r"(?i)\b(?:nonagenarian|(?:super)?centenarian)s?\b"
CLINICAL_NEGATION_PREFIX_PATTERN: Final = (
    r"(?i)\b(?:no|without|denies|negative for|history of|with|has|mild|moderate|"
    r"severe|possible|probable|suspected|early|late)\s+$"
)
CLINICAL_RANGE_GAP_PATTERN: Final = r"[\s.,;:!?()\[\]{}'\"’/-]*"
NARRATIVE_VERB_PATTERN: Final = (
    r"(?:visit(?:s|ed)|return(?:s|ed)|call(?:s|ed)|arriv(?:es|ed)|"
    r"report(?:s|ed)|assist(?:s|ed)|accompan(?:ies|ied)|attend(?:s|ed)|"
    r"declin(?:es|ed)|agree(?:s|d)|confirm(?:s|ed)|request(?:s|ed))"
)
NAME_TRAILING_VERB_PATTERN: Final = rf"[ \t]+{NARRATIVE_VERB_PATTERN}$"
ROLE_NARRATIVE_VERB_PATTERN: Final = rf"[ \t]+(?P<verb>{NARRATIVE_VERB_PATTERN})\b"
NER_DIGIT_CUE_PATTERN: Final = r"\d+"
NER_NUMBER_WORD_PATTERN: Final = (
    r"(?i)\b(?:zero|oh|one|two|three|four|five|six|seven|eight|nine|ten|eleven|"
    r"twelve|thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|"
    r"twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety|hundred|thousand)\b"
)
NER_TIME_WORD_PATTERN: Final = (
    r"(?i)\b(?:noon|midnight|morning|afternoon|evening|night|o.clock|am|pm)\b"
)
NER_DATE_WORD_PATTERN: Final = (
    r"(?i)\b(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|"
    r"jul(?:y)?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|"
    r"dec(?:ember)?|mon(?:day)?|tue(?:sday)?|wed(?:nesday)?|thu(?:rsday)?|"
    r"fri(?:day)?|sat(?:urday)?|sun(?:day)?|today|tomorrow|yesterday|"
    r"day|week|month|year|spring|summer|autumn|fall|winter|birthday)\b"
)
NER_EMAIL_CUE_PATTERN: Final = r"(?i)@|\b(?:at|dot)\b"
NER_URL_CUE_PATTERN: Final = (
    r"(?i)\b(?:[a-z0-9-]+\.)+[a-z]{2,}\b|\bwww\.|"
    r"\b[a-z][a-z0-9+.-]*:[^\s]|//|[a-z0-9]/[a-z0-9]|\b(?:dot|slash)\b"
)
# Optional model evaluation candidates
EVALUATION_OPENMED_TYPES: Final = (
    ("person", ("first_name", "last_name")),
    ("organization", ("company_name",)),
    (
        "location",
        ("street_address", "city", "state", "county", "postcode", "coordinate"),
    ),
    ("date", ("date", "date_of_birth", "date_time")),
    ("time", ("time",)),
    ("age", ("age",)),
    ("contact", ("email", "phone_number", "fax_number", "ipv4", "ipv6", "url")),
    (
        "identifier",
        (
            "account_number",
            "certificate_license_number",
            "device_identifier",
            "health_plan_beneficiary_number",
            "medical_record_number",
            "ssn",
            "unique_id",
            "vehicle_identifier",
            "license_plate",
            "user_name",
            "customer_id",
            "employee_id",
            "tax_id",
            "biometric_identifier",
            "mac_address",
            "credit_debit_card",
            "bank_routing_number",
            "swift_bic",
        ),
    ),
)
EVALUATION_OPENROUTER_URL: Final = "https://openrouter.ai/api/v1"
EVALUATION_OPENROUTER_KEY: Final = "OPENROUTER_KEY"
EVALUATION_REMOTE_VERSION: Final = "model-comparison-v1"
EVALUATION_REPLAY_HIT: Final = "cache_hits"
EVALUATION_REPLAY_MISS: Final = "cache_misses"
EVALUATION_REPLAY_REMOTE: Final = "grounded_remote_responses"
EVALUATION_REPLAY_LOCAL: Final = "cached_local_decisions"
EVALUATION_REMOTE_STATE: Final = "tmp/model-comparison-state"
EVALUATION_REMOTE_MODELS: Final = (
    "deepseek/deepseek-v4.1-flash-1017",
    "deepseek/deepseek-v4-pro",
    "z-ai/glm-5.3-flash",
)
EVALUATION_REMOTE_INPUT_PRICE: Final = "3.00"
EVALUATION_REMOTE_OUTPUT_PRICE: Final = "10.00"
EVALUATION_REMOTE_TIMEOUT: Final = 30.0
EVALUATION_REMOTE_DEADLINE: Final = 65.0
EVALUATION_REMOTE_OUTPUT_TOKENS: Final = 2048
EVALUATION_REMOTE_RECEIPTS: Final = "receipts.jsonl"
EVALUATION_OCR_CORPUS: Final = "tmp/ocr-corpus/manifest.json"
EVALUATION_OCR_DIRECTORY: Final = "tmp/ocr-corpus"
EVALUATION_OCR_COVERAGE: Final = 0.9
EVALUATION_OCR_VARIANTS: Final = ("clean", "rotated", "blurred", "low_contrast")
EVALUATION_KEY_FILENAME: Final = "encryption.key"
EVALUATION_IMAGE_FIELD: Final = "evaluation_image_base64"
EVALUATION_OCR_PROMPT_VERSION: Final = "evaluation-ocr-v1"
EVALUATION_VISION_INPUT_BYTES: Final = 2 * 1024 * 1024
EVALUATION_VISION_OUTPUT_TOKENS: Final = 4096
EVALUATION_VISION_INPUT_PRICE: Final = "0.4"
EVALUATION_VISION_OUTPUT_PRICE: Final = "1.5"
EVALUATION_REMOTE_ATTEMPTS: Final = 2
EVALUATION_OPENMED_CONFIG: Final = "config.json"
EVALUATION_OPENMED_LABELS: Final = "id2label.json"
EVALUATION_OPENMED_WEIGHTS: Final = "model_int8.onnx"

# Optional read-only monitoring
MonitorStatus = Literal["ready", "missing", "busy", "unavailable"]
MonitorStep = Literal[
    "inspect",
    "analyze",
    "resolve",
    "rewrite",
    "verify",
    "publish",
    "quarantine",
    "reconcile",
    "print_task",
]
MONITOR_READY: Final = "ready"
MONITOR_MISSING: Final = "missing"
MONITOR_BUSY: Final = "busy"
MONITOR_UNAVAILABLE: Final = "unavailable"
MONITOR_MAX_RUNS: Final = 30
MONITOR_MAX_TASKS: Final = 50
MONITOR_QUERY_SECONDS: Final = 0.1
MONITOR_SQLITE_TIMEOUT_SECONDS: Final = 0.025
MONITOR_PROGRESS_INSTRUCTIONS: Final = 1000
MONITOR_SQLITE_ERROR_MASK: Final = 0xFF
MONITOR_RUN_ID_PATTERN: Final = rf"^(?:[0-9a-f]{{64}}|{BOOTSTRAP_PROCESSING_VERSION})$"
MONITOR_STEPS: Final = (
    STEP_INSPECT,
    STEP_ANALYZE,
    STEP_RESOLVE,
    STEP_REWRITE,
    STEP_VERIFY,
    STEP_PUBLISH,
    STEP_QUARANTINE,
    STEP_RECONCILE,
    PRINT_TASK_STEP,
)
MONITOR_TASK_STATUSES: Final = (
    STATUS_PENDING,
    STATUS_RUNNING,
    STATUS_SUCCEEDED,
    STATUS_FAILED,
)
MONITOR_MAX_STEP_GROUPS: Final = len(MONITOR_STEPS) * len(MONITOR_TASK_STATUSES)
MONITOR_HOST: Final = "127.0.0.1"
MONITOR_PORT: Final = 8765
MONITOR_POLL_SECONDS: Final = 5
MONITOR_CACHE_SECONDS: Final = 5
MONITOR_BENCHMARK_DIRECTORY: Final = "benchmarks"
MONITOR_IMAGE_DIRECTORY: Final = "tmp/ocr-corpus"
MONITOR_MAX_BENCHMARK_BYTES: Final = 2 * 1024 * 1024
MONITOR_MAX_BENCHMARK_FILES: Final = 100
MONITOR_MAX_IMAGE_BYTES: Final = 8 * 1024 * 1024
MONITOR_MAX_REQUEST_PATH: Final = 256
MONITOR_BENCHMARK_IMAGE_CASE_PATTERN: Final = (
    r"^(?:synthetic-[12]|wristband)-(?:clean|rotated|blurred|low_contrast)$"
)
MONITOR_BENCHMARK_IMAGE_URL_TEMPLATE: Final = "/benchmark-images/{case_id}.png"
MONITOR_BENCHMARK_MANIFEST: Final = "manifest.json"
MONITOR_MAX_BENCHMARK_CASES: Final = 1000
MONITOR_BENCHMARK_CASE_PATTERN: Final = r"^[a-z0-9][a-z0-9_-]{0,79}$"
MONITOR_BENCHMARK_FILENAME_PATTERN: Final = r"^[a-z0-9][a-z0-9._-]{0,127}\.json$"
MONITOR_STATIC_DIRECTORY: Final = "static"
MONITOR_JSON_CONTENT_TYPE: Final = "application/json; charset=utf-8"
MONITOR_IMAGE_CONTENT_TYPE: Final = "image/png"
MONITOR_STATIC_FILES: Final = (
    ("index.html", "text/html; charset=utf-8"),
    ("styles.css", "text/css; charset=utf-8"),
    ("app.js", "text/javascript; charset=utf-8"),
    ("queue.js", "text/javascript; charset=utf-8"),
    ("queue_views.js", "text/javascript; charset=utf-8"),
    ("benchmarks.js", "text/javascript; charset=utf-8"),
    ("benchmark_details.js", "text/javascript; charset=utf-8"),
    ("format.js", "text/javascript; charset=utf-8"),
)
MONITOR_BENCHMARK_CACHE_SECONDS: Final = 30
MONITOR_QUEUE_ROUTE: Final = "/api/queue"
MONITOR_BENCHMARK_ROUTE: Final = "/api/benchmarks"
MONITOR_ASSET_PREFIX: Final = "/static/"
MONITOR_HTTP_HEADERS: Final = (
    ("Cache-Control", "no-store"),
    ("X-Content-Type-Options", "nosniff"),
    (
        "Content-Security-Policy",
        "default-src 'self'; script-src 'self'; style-src 'self'; "
        "img-src 'self'; connect-src 'self'; object-src 'none'; "
        "base-uri 'none'; frame-ancestors 'none'",
    ),
)
MONITOR_RUN_PATTERN: Final = rf"(?:[0-9a-f]{{64}}|{BOOTSTRAP_PROCESSING_VERSION})"
MONITOR_QUERY_LIMIT: Final = 2
MONITOR_MODULE: Final = "redactor.monitoring"
MONITOR_DEFAULT_ENABLED: Final = True
MONITOR_STARTUP_SECONDS: Final = 1.0
MONITOR_STOP_SECONDS: Final = 0.5
MONITOR_SERVER_POLL_SECONDS: Final = 0.5
MONITOR_REQUEST_TIMEOUT_SECONDS: Final = 1.0
MONITOR_READY_TOKEN: Final = b"ready\n"
MONITOR_MAX_PORT: Final = 65535
# Word XML scalar types and public built-in style names, scoped to Office namespaces.
DOCX_NUMERIC_ATTRIBUTES: Final = (
    "w",
    "h",
    "x",
    "y",
    "cx",
    "cy",
    "sz",
    "space",
    "before",
    "after",
    "line",
    "left",
    "right",
    "top",
    "bottom",
    "header",
    "footer",
    "gutter",
    "hanging",
    "firstLine",
    "pos",
    "count",
    "numId",
    "abstractNumId",
    "ilvl",
    "id",
    "size",
    "uiPriority",
    "unhideWhenUsed",
    "semiHidden",
    "qFormat",
    "customStyle",
    "default",
    "defLockedState",
    "defUIPriority",
    "defSemiHidden",
    "defUnhideWhenUsed",
    "defQFormat",
    "rotWithShape",
    "blurRad",
    "dist",
    "dir",
    "ang",
    "scaled",
    "lat",
    "lon",
    "rev",
    "l",
    "t",
    "r",
    "b",
    "idx",
    "noChangeAspect",
    "noChangeArrowheads",
    "spidmax",
    "data",
    "rsidR",
    "rsidRPr",
    "rsidRDefault",
    "rsidP",
    "rsidSect",
    "rsidDel",
)
DOCX_NUMERIC_ELEMENTS: Final = (
    "uiPriority",
    "tblStyleRowBandSize",
    "tblStyleColBandSize",
    "sz",
    "szCs",
    "outlineLvl",
    "numId",
    "abstractNumId",
    "start",
    "ilvl",
    "kern",
    "spacing",
    "satMod",
    "tint",
    "shade",
    "alpha",
    "defaultTabStop",
    "smallFrac",
    "lMargin",
    "rMargin",
    "wrapIndent",
    "defaultImageDpi",
    "b",
    "bCs",
    "i",
    "iCs",
    "keepNext",
    "keepLines",
    "widowControl",
    "snapToGrid",
    "cantSplit",
)
DOCX_HEX_ELEMENTS: Final = ("rsid", "rsidRoot", "nsid", "tmpl", "panose1", "charset")
DOCX_FORMAT_ENUMS: Final = (
    (
        "type",
        "paragraph|character|table|numbering|dxa|pct|auto|nil|band[12](?:Horz|Vert)|first(?:Col|Row)|last(?:Col|Row)|[ns][ew]Cell",
    ),
    (
        "val",
        "clear|nil|single|double|dotted|dashed|thick|wave|dashSmallGap|dotDash|dotDotDash|none|left|right|center|both|distribute|num|decimal|bullet|lowerLetter|upperLetter|lowerRoman|upperRoman|singleLevel|multilevel|hybridMultilevel|bestFit|fullPage|textFit|doNotCompress|before|after|centerGroup|subSup|undOvr|--|[.,]",
    ),
    (
        "themeColor",
        "(?:accent[1-6]|background[12]|text[12]|dark[12]|light[12]|hyperlink|followedHyperlink|none)",
    ),
    (
        "themeFill",
        "(?:accent[1-6]|background[12]|text[12]|dark[12]|light[12]|hyperlink|followedHyperlink|none)",
    ),
    ("lineRule", "auto|exact|atLeast"),
    ("asciiTheme", "(?:major|minor)(?:Ascii|HAnsi|EastAsia|Bidi)"),
    ("eastAsiaTheme", "(?:major|minor)(?:Ascii|HAnsi|EastAsia|Bidi)"),
    ("hAnsiTheme", "(?:major|minor)(?:Ascii|HAnsi|EastAsia|Bidi)"),
    ("cstheme", "(?:major|minor)(?:Ascii|HAnsi|EastAsia|Bidi)"),
    ("hint", "default|eastAsia|cs"),
    ("spelling", "clean|dirty"),
    ("grammar", "clean|dirty"),
    ("baseType", "variant|lpstr|lpwstr|i4"),
    ("family", "auto|decorative|modern|roman|script|swiss"),
    ("pitch", "default|fixed|variable"),
)
DOCX_BUILTIN_STYLE_PATTERN: Final = (
    r"(?i)(?:Normal|No\s*Spacing|Default\s*Paragraph\s*Font|Table\s*(?:Normal|Grid)|"
    r"No\s*List|Heading\s*[1-9]|TOC\s*Heading|Title|Subtitle|Caption|Header|Footer|"
    r"Body\s*Text\s*[23]?|List\s*(?:Bullet|Number|Continue|Paragraph)?\s*[1-9]?|"
    r"(?:Intense|Subtle)?\s*(?:Emphasis|Reference)|Strong|(?:Intense\s*)?Quote|"
    r"Macro\s*Text|Book\s*Title|Comment\s*(?:Text|Reference|Subject)|"
    r"(?:Light|Medium|Dark|Colorful)\s*(?:Shading|List|Grid)\s*[1-3]?"
    r"(?:\s*[- ]\s*Accent\s*[1-6])?)(?:\s*Char)?"
)
DOCX_STYLE_ELEMENTS: Final = (
    "name",
    "basedOn",
    "next",
    "link",
    "pStyle",
    "rStyle",
    "tblStyle",
)
DOCX_SCHEMA_NAMESPACES: Final = (
    OOXML_DC_TYPE_NAMESPACE,
    "http://schemas.microsoft.com/office/drawing/2010/main",
    "http://schemas.microsoft.com/office/mac/office/2008/main",
    "http://schemas.microsoft.com/office/word/2006/wordml",
    "http://schemas.microsoft.com/office/word/2010/wordprocessingCanvas",
    "http://schemas.microsoft.com/office/word/2010/wordprocessingGroup",
    "http://schemas.microsoft.com/office/word/2010/wordprocessingInk",
    "http://schemas.microsoft.com/office/word/2010/wordprocessingShape",
    "http://schemas.openxmlformats.org/schemaLibrary/2006/main",
    "urn:schemas-microsoft-com:mac:vml",
    "urn:schemas-microsoft-com:office:word",
    DOCX_WORD_NAMESPACE,
    OOXML_DRAWING_NAMESPACE,
    OOXML_RELATIONSHIP_NAMESPACE,
    OOXML_CONTENT_NAMESPACE,
    OOXML_OFFICE_RELATIONSHIP_NAMESPACE,
    OOXML_CORE_NAMESPACE,
    OOXML_EXTENDED_NAMESPACE,
    OOXML_DC_NAMESPACE,
    OOXML_DC_TERMS_NAMESPACE,
    XML_NAMESPACE,
    XML_SCHEMA_INSTANCE_NAMESPACE,
    "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing",
    "http://schemas.openxmlformats.org/drawingml/2006/picture",
    "http://schemas.openxmlformats.org/officeDocument/2006/math",
    "http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes",
    "http://schemas.openxmlformats.org/officeDocument/2006/bibliography",
    "http://schemas.openxmlformats.org/officeDocument/2006/customXml",
    "http://schemas.microsoft.com/office/word/2010/wordml",
    "http://schemas.microsoft.com/office/word/2012/wordml",
    "http://schemas.microsoft.com/office/word/2010/wordprocessingDrawing",
    "http://schemas.openxmlformats.org/markup-compatibility/2006",
    "urn:schemas-microsoft-com:office:office",
    "urn:schemas-microsoft-com:vml",
)
DOCX_PUBLIC_URIS: Final = (
    "http://schemas.openxmlformats.org/drawingml/2006/picture",
    "http://schemas.microsoft.com/office/word",
    "http://schemas.openxmlformats.org/officeDocument/2006/bibliography",
)
DOCX_PACKAGE_PART_PATTERN: Final = (
    r"(?:\[Content_Types\]\.xml|_rels/\.rels|docProps/(?:core|app|custom)\.xml|"
    r"docProps/thumbnail\.(?:jpeg|jpg|png)|"
    r"word/(?:document|styles|stylesWithEffects|settings|webSettings|fontTable|numbering|"
    r"comments|commentsExtended|footnotes|endnotes|header[0-9]+|footer[0-9]+)\.xml|"
    r"word/theme/theme[0-9]+\.xml|word/media/image[0-9]+\.(?:png|jpe?g|tiff?)|"
    r"customXml/(?:item|itemProps)[0-9]+\.xml|"
    r"(?:word|customXml)/_rels/[A-Za-z]+[0-9]*\.xml\.rels)"
)

# PDF native surfaces and conservative rewriting.
PDF_TEXT_PART: Final = "pdf-page"
PDF_METADATA_PART: Final = "pdf-metadata"
PDF_ATTACHMENT_PART: Final = "pdf-attachment"
PDF_IMAGE_PART: Final = "pdf-image"
PDF_GARBAGE_LEVEL: Final = 4
PDF_MINIMUM_FONT_SIZE: Final = 4.0
PDF_METADATA_FIELDS: Final = (
    "title",
    "author",
    "subject",
    "keywords",
    "creator",
    "producer",
    "creationDate",
    "modDate",
)
PDF_UNSUPPORTED_KEYS: Final = (
    "AA",
    "Collection",
    "JavaScript",
    "JS",
    "Launch",
    "OCProperties",
    "OpenAction",
    "PageLabels",
    "RichMediaContent",
    "StructTreeRoot",
    "Thumb",
    "XFA",
)
PDF_FONT_NAMES: Final = (
    "Helvetica",
    "Helvetica-Bold",
    "Helvetica-Oblique",
    "Helvetica-BoldOblique",
    "Times-Roman",
    "Times-Bold",
    "Times-Italic",
    "Times-BoldItalic",
    "Courier",
    "Courier-Bold",
    "Courier-Oblique",
    "Courier-BoldOblique",
)
DICOM_CONTEXT: Final = "dicom"
DICOM_FILE_META_LOCATION: Final = "file_meta"
DICOM_RESERVED_ATTRIBUTES: Final = (
    "IconImageSequence",
    "DigitalSignaturesSequence",
    "MACParametersSequence",
    "EncryptedAttributesSequence",
    "OriginalAttributesSequence",
    "DataSetTrailingPadding",
)

PDF_XMP_PART: Final = "pdf-xmp"
PDF_ANNOTATION_PART: Final = "pdf-annotation"
PDF_WIDGET_PART: Final = "pdf-widget"
PDF_OUTLINE_PART: Final = "pdf-outline"

# Recognized Office XML vocabulary; other labels are assessed as text.
DOCX_SCHEMA_LABELS: Final = (
    "AppVersion",
    "Application",
    "Characters",
    "CharactersWithSpaces",
    "Company",
    "ContentType",
    "Default",
    "DocSecurity",
    "Extension",
    "HeadingPairs",
    "HyperlinkBase",
    "HyperlinksChanged",
    "Id",
    "Ignorable",
    "Lines",
    "LinksUpToDate",
    "Manager",
    "Override",
    "Pages",
    "Paragraphs",
    "PartName",
    "Properties",
    "Relationship",
    "Relationships",
    "ScaleCrop",
    "SelectedStyle",
    "SharedDoc",
    "Sources",
    "StyleName",
    "Target",
    "TargetMode",
    "Template",
    "TitlesOfParts",
    "TotalTime",
    "Type",
    "Types",
    "Words",
    "abstractNum",
    "abstractNumId",
    "accent1",
    "accent2",
    "accent3",
    "accent4",
    "accent5",
    "accent6",
    "after",
    "algn",
    "allowPNG",
    "alpha",
    "ang",
    "annotationRef",
    "ascii",
    "asciiTheme",
    "author",
    "b",
    "bCs",
    "baseType",
    "basedOn",
    "before",
    "bevelT",
    "bg1",
    "bg2",
    "bgFillStyleLst",
    "bidi",
    "blip",
    "blipFill",
    "blurRad",
    "body",
    "bodyPr",
    "bottom",
    "brkBin",
    "brkBinSub",
    "cNvGraphicFramePr",
    "cNvPicPr",
    "cNvPr",
    "camera",
    "cap",
    "category",
    "characterSpacingControl",
    "charset",
    "clrScheme",
    "clrSchemeMapping",
    "cmpd",
    "color",
    "cols",
    "comment",
    "commentRangeEnd",
    "commentRangeStart",
    "commentReference",
    "comments",
    "compat",
    "compatSetting",
    "contextualSpacing",
    "coreProperties",
    "count",
    "created",
    "creator",
    "cs",
    "csb0",
    "csb1",
    "cstheme",
    "customStyle",
    "cx",
    "cy",
    "data",
    "datastoreItem",
    "date",
    "decimalSymbol",
    "defJc",
    "defLockedState",
    "defQFormat",
    "defSemiHidden",
    "defUIPriority",
    "defUnhideWhenUsed",
    "default",
    "defaultImageDpi",
    "defaultTabStop",
    "del",
    "delText",
    "descr",
    "description",
    "dir",
    "dispDef",
    "dist",
    "dk1",
    "dk2",
    "doNotAutoCompressPictures",
    "doNotSaveAsSingleFile",
    "docDefaults",
    "docGrid",
    "docId",
    "docPr",
    "document",
    "drawing",
    "ea",
    "eastAsia",
    "eastAsiaTheme",
    "effectLst",
    "effectRef",
    "effectStyle",
    "effectStyleLst",
    "embed",
    "ext",
    "extent",
    "extraClrSchemeLst",
    "family",
    "fill",
    "fillRect",
    "fillRef",
    "fillStyleLst",
    "fillToRect",
    "firstColumn",
    "firstRow",
    "fmtScheme",
    "folHlink",
    "followedHyperlink",
    "font",
    "fontRef",
    "fontScheme",
    "fonts",
    "footer",
    "footerReference",
    "ftr",
    "gradFill",
    "grammar",
    "graphic",
    "graphicData",
    "graphicFrameLocks",
    "gridCol",
    "gs",
    "gsLst",
    "gutter",
    "h",
    "hAnsi",
    "hAnsiTheme",
    "hanging",
    "hdr",
    "header",
    "headerReference",
    "hint",
    "hlink",
    "hyperlink",
    "i",
    "i4",
    "iCs",
    "id",
    "idmap",
    "idx",
    "ilvl",
    "ind",
    "initials",
    "inline",
    "insideH",
    "insideV",
    "intLim",
    "itemID",
    "keepLines",
    "keepNext",
    "kern",
    "keywords",
    "l",
    "lMargin",
    "lang",
    "lastClr",
    "lastColumn",
    "lastModifiedBy",
    "lastRow",
    "lat",
    "latentStyles",
    "latin",
    "left",
    "lightRig",
    "lin",
    "line",
    "linePitch",
    "lineRule",
    "link",
    "listSeparator",
    "ln",
    "lnDef",
    "lnRef",
    "lnStyleLst",
    "lon",
    "lpstr",
    "lsdException",
    "lstStyle",
    "lt1",
    "lt2",
    "lvl",
    "lvlJc",
    "lvlText",
    "majorFont",
    "mathFont",
    "mathPr",
    "minorFont",
    "modified",
    "multiLevelType",
    "name",
    "naryLim",
    "next",
    "noChangeAspect",
    "noHBand",
    "noVBand",
    "notTrueType",
    "nsid",
    "num",
    "numFmt",
    "numId",
    "numPr",
    "numbering",
    "nvPicPr",
    "objectDefaults",
    "off",
    "outerShdw",
    "outlineLvl",
    "p",
    "pBdr",
    "pPr",
    "pPrDefault",
    "pStyle",
    "panose1",
    "path",
    "pgMar",
    "pgSz",
    "pic",
    "pitch",
    "pos",
    "proofState",
    "prst",
    "prstDash",
    "prstGeom",
    "qFormat",
    "r",
    "rFonts",
    "rMargin",
    "rPr",
    "rPrDefault",
    "rStyle",
    "rev",
    "revision",
    "rig",
    "right",
    "rot",
    "rotWithShape",
    "rsid",
    "rsidR",
    "rsidRPr",
    "rsidRoot",
    "rsidSect",
    "rsids",
    "satMod",
    "savePreviewPicture",
    "scaled",
    "scene3d",
    "schemaRef",
    "schemaRefs",
    "schemeClr",
    "script",
    "sectPr",
    "semiHidden",
    "settings",
    "shade",
    "shapeDefaults",
    "shapedefaults",
    "shapelayout",
    "shd",
    "sig",
    "size",
    "smallCaps",
    "smallFrac",
    "solidFill",
    "sp3d",
    "spDef",
    "spPr",
    "space",
    "spacing",
    "spelling",
    "spidmax",
    "srgbClr",
    "start",
    "stretch",
    "style",
    "styleId",
    "styles",
    "subject",
    "sysClr",
    "sz",
    "szCs",
    "t",
    "t1",
    "t2",
    "tab",
    "tabs",
    "tbl",
    "tblBorders",
    "tblCellMar",
    "tblGrid",
    "tblInd",
    "tblLook",
    "tblPr",
    "tblStyle",
    "tblStyleColBandSize",
    "tblStylePr",
    "tblStyleRowBandSize",
    "tblW",
    "tc",
    "tcBorders",
    "tcPr",
    "tcW",
    "theme",
    "themeColor",
    "themeElements",
    "themeFill",
    "themeFillShade",
    "themeFillTint",
    "themeFontLang",
    "themeShade",
    "themeTint",
    "tint",
    "title",
    "tmpl",
    "top",
    "tr",
    "type",
    "typeface",
    "u",
    "uiPriority",
    "unhideWhenUsed",
    "uri",
    "usb0",
    "usb1",
    "usb2",
    "usb3",
    "useFELayout",
    "val",
    "vanish",
    "variant",
    "vector",
    "w",
    "webSettings",
    "wrapIndent",
    "x",
    "xfrm",
    "y",
    "zoom",
)
DOCX_SCHEMA_PREFIXES: Final = (
    "w10",
    "wne",
    "wpc",
    "wpg",
    "wpi",
    "wps",
    "a14",
    "sl",
    "mo",
    "mv",
    "a",
    "b",
    "cp",
    "dc",
    "dcterms",
    "ds",
    "m",
    "mc",
    "ns0",
    "ns1",
    "ns2",
    "o",
    "pic",
    "r",
    "v",
    "vt",
    "w",
    "w14",
    "wp",
    "wp14",
    "xsi",
)

# DICOM short strings and shared identifier namespaces.
SHORT_IDENTIFIER_NAMESPACES: Final = (
    "accession",
    "procedure_step",
    "procedure_request",
    "dicom_implementation",
)
SHORT_IDENTIFIER_DIGITS: Final = 16
DICOM_STRING_LIMITS: Final = (("SH", 16), ("AE", 16), ("LO", 64), ("UI", 64))

DICOM_BINARY_VRS: Final = ("OB", "OW", "OF", "OD", "OL", "OV", "UN")

# FHIR primitive extensions retain an explicit bounded age without a precise DOB.
FHIR_DATA_ABSENT_REASON_URL: Final = (
    "http://hl7.org/fhir/StructureDefinition/data-absent-reason"
)
FHIR_AGE_BAND_URL: Final = "urn:redactor:structure-definition:age-band"
FHIR_BIRTH_BOUND_URL: Final = "urn:redactor:structure-definition:birth-date-upper-bound"
# Model subtypes that have deterministic identifier replacements.
NER_IDENTIFIER_NAMESPACES: Final = (
    ("medical record number", MRN_NAMESPACE),
    ("account number", ACCOUNT_NAMESPACE),
    ("device identifier", "device"),
    ("driver license", "driver_license"),
)
NER_IDENTIFIER_VALUE_PATTERN: Final = r"[A-Za-z0-9][A-Za-z0-9./_-]*"

NER_IP_CUE_PATTERN: Final = (
    r"(?i)(?:[0-9]{1,3}\.){3}[0-9]{1,3}|(?:[0-9a-f]*:){2}|"
    r"(?:\[dot\]|\(dot\)).*(?:\[dot\]|\(dot\))"
)

ORGANIZATION_SURROGATE_PREFIX: Final = "Organization "
ORGANIZATION_CUE_PATTERN: Final = (
    r"(?i)\b(?:hospital|clinic|medical|health|healthcare|university|insurance|"
    r"association|corporation|inc|ltd|llc)\b"
)
ORGANIZATION_FIELD_PATTERN: Final = (
    r"(?i)\b(?:payer|insurer|insurance|organization|institution|facility)\s*:\s*$"
)

LOCAL_ENVIRONMENT_FILENAME: Final = ".env.local"
