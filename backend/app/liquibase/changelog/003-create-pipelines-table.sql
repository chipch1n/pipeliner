CREATE TABLE IF NOT EXISTS pipelines (
    id              SERIAL PRIMARY KEY,
    user_id         INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name            VARCHAR(255) NOT NULL,
    pipeline_data   JSONB NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(user_id, name)
);

CREATE INDEX IF NOT EXISTS idx_pipelines_user_id ON pipelines(user_id);
CREATE INDEX IF NOT EXISTS idx_pipelines_user_id_name ON pipelines(user_id, name);