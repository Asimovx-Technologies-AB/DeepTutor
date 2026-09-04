-- Azure PostgreSQL vector and hybrid-search storage for DeepTutor.
-- PGVECTOR_DIMENSIONS is 768 and must match the embedding provider (Gemini).
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS document_chunks (
    id              text PRIMARY KEY,
    topic_id        text NOT NULL,
    chunk_text      text NOT NULL,
    metadata        jsonb NOT NULL DEFAULT '{}'::jsonb,
    embedding       vector(768) NOT NULL,
    search_vector   tsvector GENERATED ALWAYS AS (
        to_tsvector('simple', coalesce(chunk_text, ''))
    ) STORED,
    created_at      timestamptz NOT NULL DEFAULT now(),
    updated_at      timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_document_chunks_topic
    ON document_chunks (topic_id);

CREATE INDEX IF NOT EXISTS ix_document_chunks_metadata
    ON document_chunks USING gin (metadata);

CREATE INDEX IF NOT EXISTS ix_document_chunks_search
    ON document_chunks USING gin (search_vector);

CREATE INDEX IF NOT EXISTS ix_document_chunks_embedding_hnsw
    ON document_chunks USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);
