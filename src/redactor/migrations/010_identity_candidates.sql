CREATE INDEX identity_candidates_by_identifier_birth
ON identity_observations(identifier_key, birth_key, is_anchor, task_id);
