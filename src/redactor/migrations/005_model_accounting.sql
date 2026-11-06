CREATE TABLE model_attempts (
    attempt_id INTEGER PRIMARY KEY,
    request_key TEXT NOT NULL,
    task_id TEXT NOT NULL REFERENCES tasks(task_id),
    task_attempt_token TEXT NOT NULL,
    reserved_nanos INTEGER NOT NULL CHECK (reserved_nanos >= 0),
    charged_nanos INTEGER CHECK (charged_nanos >= 0),
    input_tokens INTEGER CHECK (input_tokens >= 0),
    output_tokens INTEGER CHECK (output_tokens >= 0),
    status TEXT NOT NULL CHECK (status IN ('reserved', 'settled', 'uncertain'))
);

CREATE INDEX model_attempts_request ON model_attempts(request_key);
CREATE INDEX model_attempts_task ON model_attempts(task_id);

CREATE TABLE model_decisions (
    request_key TEXT PRIMARY KEY,
    task_id TEXT NOT NULL REFERENCES tasks(task_id),
    encrypted_payload BLOB NOT NULL
);

CREATE TABLE model_circuits (
    processing_version TEXT PRIMARY KEY,
    failures INTEGER NOT NULL DEFAULT 0 CHECK (failures >= 0),
    retry_after REAL NOT NULL DEFAULT 0,
    disabled_reason TEXT,
    probe_attempt_id INTEGER REFERENCES model_attempts(attempt_id)
);
