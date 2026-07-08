-- Multi-turn conversation support: persist conversation/message history so
-- /answer can be called with a conversation_id and get prior turns back.
-- Run against existing databases; fresh installs get this from db/schema.sql.
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
