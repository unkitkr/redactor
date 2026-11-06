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
MODEL_PURPOSE_DETECTOR: Final = "detector"
MODEL_PURPOSE_JUDGE: Final = "judge"
HTTP_RETRY_AFTER_HEADER: Final = "retry-after"
HTTP_CONTENT_ENCODING_HEADER: Final = "content-encoding"
HTTP_IDENTITY_ENCODING: Final = "identity"

# Grounded text detection
DETECTOR_PROMPT_VERSION: Final = "text-entities-v1"
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
IDENTITY_BATCH_NAMESPACE: Final = "identity-observation-batch"
IDENTITY_BATCH_LIMIT: Final = 20_000
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
MRN_NAMESPACE: Final = "mrn"
PATIENT_ID_NAMESPACE: Final = "patient-id"
ENCOUNTER_ID_NAMESPACE: Final = "encounter-id"
ACCOUNT_NAMESPACE: Final = "account-number"
RELATIVE_NAME_NAMESPACE: Final = "relative-name"
IDENTITY_PATIENT: Final = "patient"
IDENTITY_RELATIVE: Final = "relative"
ROW_CONTEXT_TEMPLATE: Final = "{input_sha256}:row:{number}:{role}"
TABULAR_FIELD_ALIASES: Final = (
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
    ("icd", r"[A-Z][0-9][0-9A-Z](?:\.[0-9A-Z]{1,4})?"),
    ("procedure", r"(?:[0-9]{5}|[A-Z][0-9]{4}|[0-9]{4}[A-Z])"),
    ("loinc", r"[0-9]{1,7}-[0-9]"),
    ("ndc", r"(?:[0-9]{10,11}|[0-9]{4,5}-[0-9]{3,4}-[0-9]{1,2})"),
    ("rxnorm", r"[0-9]+"),
    ("quantity", r"[<>≤≥]?[+-]?[0-9]+(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?"),
    ("sex", r"(?:M|F|O|U|male|female|other|unknown)"),
    ("unit", r"(?:%|[a-zA-Zµμ]+(?:\^[0-9]+)?(?:/[a-zA-Zµμ]+(?:\^[0-9]+)?)?)"),
)
CLINICAL_CODE_SEPARATOR_PATTERN: Final = r"[;,|\s]+"
AGE_EXPLICIT_PATTERN: Final = (
    r"(?i)\bage\s*[:=]?\s*(?P<age>[0-9]{1,3})(?:\+)?\b"
    r"(?!\s*(?:days?|weeks?|months?)\b)"
)

# Free-text evidence. These are field-independent clinical and PHI patterns.
TEXT_EMAIL_PATTERN: Final = r"(?<![\w.+-])[\w.+-]+@[\w-]+(?:\.[\w-]+)+(?![\w-])"
TEXT_PHONE_PATTERN: Final = (
    r"(?<![\w])(?:\+?1[ .-]?)?(?:\([2-9][0-9]{2}\)|[2-9][0-9]{2})"
    r"[ .-]?[0-9]{3}[ .-]?[0-9]{4}(?![\w])"
)
TEXT_DATE_PATTERN: Final = (
    r"(?<![\w/])(?:[0-9]{4}[-/][0-9]{1,2}[-/][0-9]{1,2}"
    r"|[0-9]{1,2}/[0-9]{1,2}/[0-9]{4})(?![\w/])"
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
TEXT_CLINICAL_PATTERNS: Final = (
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
