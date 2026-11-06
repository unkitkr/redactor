CREATE TABLE identity_observations (
    task_id TEXT NOT NULL REFERENCES tasks(task_id),
    observation_key TEXT NOT NULL,
    identifier_key TEXT,
    name_key TEXT,
    birth_key TEXT,
    is_anchor INTEGER NOT NULL CHECK (is_anchor IN (0, 1)),
    encrypted_payload BLOB NOT NULL,
    PRIMARY KEY (task_id, observation_key)
);

CREATE INDEX identity_identifier_candidates
    ON identity_observations(identifier_key, is_anchor);
CREATE INDEX identity_demographic_candidates
    ON identity_observations(name_key, birth_key, is_anchor);

CREATE TABLE identity_scan_progress (
    task_id TEXT PRIMARY KEY REFERENCES tasks(task_id),
    sequence INTEGER NOT NULL CHECK (sequence > 0),
    input_offset INTEGER NOT NULL CHECK (input_offset >= 0),
    record_count INTEGER NOT NULL CHECK (record_count >= 0),
    batch_digest TEXT NOT NULL
);
