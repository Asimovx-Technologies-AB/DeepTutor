-- Azure PostgreSQL vector and hybrid-search storage for DeepTutor.
-- PGVECTOR_DIMENSIONS is 1536 and must match the embedding provider (OpenAI / Azure OpenAI text-embedding-3-small).
CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE EXTENSION IF NOT EXISTS vector;

-- Migration safety: If an incompatible legacy table with TEXT id or non-1536 dimension exists,
-- drop it to allow creating the canonical UUID + vector(1536) schema.
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'document_chunks' AND column_name = 'id' AND data_type = 'text'
    ) THEN
        DROP TABLE document_chunks CASCADE;
    END IF;
END $$;

CREATE TABLE IF NOT EXISTS document_chunks (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id      TEXT NOT NULL DEFAULT '',
    topic_id        TEXT NOT NULL,
    doc_id          TEXT DEFAULT '',
    chunk_id        TEXT DEFAULT '',
    page            INT DEFAULT 1,
    source_type     TEXT DEFAULT 'text',
    chunk_text      TEXT NOT NULL,
    metadata        JSONB NOT NULL DEFAULT '{}'::jsonb,
    embedding       vector(1536) NOT NULL,
    search_vector   tsvector GENERATED ALWAYS AS (
        to_tsvector('english', coalesce(chunk_text, ''))
    ) STORED,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_document_chunks_session_id
    ON document_chunks (session_id);

CREATE INDEX IF NOT EXISTS ix_document_chunks_topic_id
    ON document_chunks (topic_id);

CREATE INDEX IF NOT EXISTS ix_document_chunks_doc_id
    ON document_chunks (doc_id);

CREATE INDEX IF NOT EXISTS ix_document_chunks_metadata
    ON document_chunks USING gin (metadata);

CREATE INDEX IF NOT EXISTS ix_document_chunks_search
    ON document_chunks USING gin (search_vector);

-- NOTE on pgvector < 0.5.0 / HNSW compatibility:
-- HNSW provides high recall (>95%) without needing training data and is available in pgvector >= 0.5.0.
-- If target server runs pgvector < 0.5.0 where HNSW is unavailable, replace HNSW with:
-- CREATE INDEX IF NOT EXISTS ix_document_chunks_embedding_ivfflat
--     ON document_chunks USING ivfflat (embedding vector_cosine_ops)
--     WITH (lists = 100);
-- Tradeoff: IVFFlat builds faster on large tables but requires pre-existing rows for clustering
-- and offers lower accuracy/recall than HNSW under high query loads.
CREATE INDEX IF NOT EXISTS ix_document_chunks_embedding_hnsw
    ON document_chunks USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);
