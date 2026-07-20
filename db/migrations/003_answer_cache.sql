-- Semantic answer cache: lets /answer skip retrieval + the answer LLM call
-- when a near-identical (query + history) was already answered for the same
-- as_of date. Run against existing databases; fresh installs get this from
-- db/schema.sql.
CREATE TABLE IF NOT EXISTS answer_cache (
    id               SERIAL PRIMARY KEY,
    as_of            DATE NOT NULL,
    query_text       TEXT NOT NULL,
    cache_key_text   TEXT NOT NULL,
    cache_embedding  vector(1024) NOT NULL,
    answer_payload   JSONB NOT NULL,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS answer_cache_embedding_hnsw ON answer_cache
    USING hnsw (cache_embedding vector_cosine_ops);

CREATE INDEX IF NOT EXISTS answer_cache_as_of_idx ON answer_cache (as_of);
