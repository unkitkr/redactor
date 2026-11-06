CREATE TABLE detection_observations (
    task_id TEXT NOT NULL REFERENCES tasks(task_id),
    observation_key TEXT NOT NULL,
    encrypted_payload BLOB NOT NULL,
    PRIMARY KEY (task_id, observation_key)
);
