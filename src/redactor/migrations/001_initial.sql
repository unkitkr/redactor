CREATE TABLE tasks (
    task_id TEXT PRIMARY KEY,
    input_path TEXT NOT NULL,
    input_sha256 TEXT NOT NULL,
    input_size INTEGER NOT NULL CHECK (input_size >= 0),
    step TEXT NOT NULL,
    processing_version TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN (
        'pending', 'running', 'succeeded', 'failed'
    )),
    attempt_token TEXT,
    attempt_count INTEGER NOT NULL DEFAULT 0,
    failure_code TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    result_path TEXT,
    result_sha256 TEXT,
    result_size INTEGER CHECK (result_size >= 0)
);

CREATE INDEX tasks_ready ON tasks (status, created_at, task_id);

CREATE TABLE dependencies (
    task_id TEXT NOT NULL REFERENCES tasks(task_id),
    depends_on TEXT NOT NULL REFERENCES tasks(task_id),
    PRIMARY KEY (task_id, depends_on),
    CHECK (task_id != depends_on)
);

CREATE TABLE attempts (
    task_id TEXT NOT NULL REFERENCES tasks(task_id),
    attempt_token TEXT PRIMARY KEY,
    status TEXT NOT NULL CHECK (status IN (
        'running', 'succeeded', 'failed', 'interrupted'
    )),
    started_at TEXT NOT NULL,
    finished_at TEXT,
    failure_code TEXT
);

CREATE INDEX attempts_by_task ON attempts (task_id, started_at);

CREATE TABLE checkpoints (
    task_id TEXT NOT NULL REFERENCES tasks(task_id),
    sequence INTEGER NOT NULL CHECK (sequence > 0),
    artifact_path TEXT NOT NULL,
    input_offset INTEGER NOT NULL CHECK (input_offset >= 0),
    output_offset INTEGER NOT NULL CHECK (output_offset >= 0),
    record_count INTEGER NOT NULL CHECK (record_count >= 0),
    output_prefix_sha256 TEXT NOT NULL,
    counts_json TEXT NOT NULL,
    PRIMARY KEY (task_id, sequence)
);
