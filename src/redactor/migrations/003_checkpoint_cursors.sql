ALTER TABLE checkpoints ADD COLUMN adapter_version TEXT NOT NULL DEFAULT 'legacy';
ALTER TABLE checkpoints ADD COLUMN cursor_json TEXT NOT NULL DEFAULT '{}';
