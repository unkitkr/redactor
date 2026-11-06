CREATE TABLE identity_resolution_sources (
    resolution_task_id TEXT NOT NULL REFERENCES tasks(task_id),
    source_task_id TEXT NOT NULL REFERENCES tasks(task_id),
    PRIMARY KEY (resolution_task_id, source_task_id)
);

CREATE TABLE identity_resolution_progress (
    resolution_task_id TEXT PRIMARY KEY REFERENCES tasks(task_id),
    source_task_id TEXT NOT NULL,
    observation_key TEXT NOT NULL,
    observation_count INTEGER NOT NULL CHECK (observation_count >= 0)
);

CREATE TABLE identity_bindings (
    resolution_task_id TEXT NOT NULL,
    source_task_id TEXT NOT NULL,
    observation_key TEXT NOT NULL,
    identity_key TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('corroborated', 'isolated', 'ambiguous')),
    binding_digest TEXT NOT NULL,
    PRIMARY KEY (resolution_task_id, source_task_id, observation_key),
    FOREIGN KEY (resolution_task_id, source_task_id)
        REFERENCES identity_resolution_sources(resolution_task_id, source_task_id),
    FOREIGN KEY (source_task_id, observation_key)
        REFERENCES identity_observations(task_id, observation_key)
);

CREATE TABLE identity_cohorts (
    resolution_task_id TEXT NOT NULL REFERENCES tasks(task_id),
    identity_key TEXT NOT NULL,
    encrypted_payload BLOB NOT NULL,
    PRIMARY KEY (resolution_task_id, identity_key)
);
