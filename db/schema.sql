CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS act (
    id        SERIAL PRIMARY KEY,
    eli       TEXT NOT NULL UNIQUE,
    title_et  TEXT NOT NULL,
    title_en  TEXT,
    domain    TEXT NOT NULL,
    act_type  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS act_version (
    id             SERIAL PRIMARY KEY,
    act_id         INTEGER NOT NULL REFERENCES act(id),
    effective_from DATE NOT NULL,
    effective_to   DATE,
    source_url     TEXT NOT NULL,
    source_hash    TEXT NOT NULL,
    source_global_id BIGINT
);

CREATE INDEX IF NOT EXISTS act_version_source_global_id_idx
    ON act_version (source_global_id);

CREATE TABLE IF NOT EXISTS provision (
    id             SERIAL PRIMARY KEY,
    act_version_id INTEGER NOT NULL REFERENCES act_version(id),
    section_num    TEXT NOT NULL,
    level          TEXT NOT NULL,
    text_et        TEXT NOT NULL,
    text_en        TEXT,
    parent_id      INTEGER,
    embedding      vector(1024)
);

CREATE INDEX IF NOT EXISTS provision_fts ON provision
    USING gin(to_tsvector('simple', text_et));

CREATE INDEX IF NOT EXISTS provision_embedding_hnsw ON provision
    USING hnsw (embedding vector_cosine_ops);

CREATE TABLE IF NOT EXISTS conversation (
    id         SERIAL PRIMARY KEY,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS message (
    id              SERIAL PRIMARY KEY,
    conversation_id INTEGER NOT NULL REFERENCES conversation(id),
    role            TEXT NOT NULL,
    content         TEXT NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS message_conversation_id_idx ON message (conversation_id);
