CREATE TABLE model_request_windows (
    request_key TEXT PRIMARY KEY,
    task_id TEXT NOT NULL REFERENCES tasks(task_id),
    deadline_at REAL NOT NULL CHECK (deadline_at >= 0),
    retry_after_at REAL NOT NULL DEFAULT 0 CHECK (retry_after_at >= 0)
);
