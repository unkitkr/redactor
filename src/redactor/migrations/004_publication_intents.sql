CREATE TABLE publication_intents (
    task_id TEXT PRIMARY KEY REFERENCES tasks(task_id),
    verification_task_id TEXT NOT NULL REFERENCES tasks(task_id),
    producer_task_id TEXT NOT NULL REFERENCES tasks(task_id),
    output_path TEXT NOT NULL,
    artifact_sha256 TEXT NOT NULL,
    artifact_size INTEGER NOT NULL CHECK (artifact_size >= 0)
);
