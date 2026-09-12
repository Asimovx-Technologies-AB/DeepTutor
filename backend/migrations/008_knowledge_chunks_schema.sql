-- Migration 008: Extend document_chunks with Knowledge Tiler metadata columns.
-- Non-destructive: existing rows get defaults or NULL for new columns.

ALTER TABLE document_chunks ADD COLUMN IF NOT EXISTS chunk_type TEXT DEFAULT 'text';
ALTER TABLE document_chunks ADD COLUMN IF NOT EXISTS topic TEXT;
ALTER TABLE document_chunks ADD COLUMN IF NOT EXISTS chapter_section TEXT;
ALTER TABLE document_chunks ADD COLUMN IF NOT EXISTS parent_chunk_id TEXT;
ALTER TABLE document_chunks ADD COLUMN IF NOT EXISTS child_chunk_ids TEXT[];
ALTER TABLE document_chunks ADD COLUMN IF NOT EXISTS named_concepts TEXT[];
ALTER TABLE document_chunks ADD COLUMN IF NOT EXISTS templates TEXT DEFAULT '';
ALTER TABLE document_chunks ADD COLUMN IF NOT EXISTS confidence FLOAT DEFAULT 0.0;
ALTER TABLE document_chunks ADD COLUMN IF NOT EXISTS provenance JSONB DEFAULT '{}'::jsonb;
ALTER TABLE document_chunks ADD COLUMN IF NOT EXISTS weight FLOAT DEFAULT 1.0;

-- Index for concept-based search
CREATE INDEX IF NOT EXISTS ix_document_chunks_concepts
    ON document_chunks USING gin (named_concepts);

-- Index for chunk type filtering
CREATE INDEX IF NOT EXISTS ix_document_chunks_type
    ON document_chunks (chunk_type);

-- Index for section hierarchy queries
CREATE INDEX IF NOT EXISTS ix_document_chunks_section
    ON document_chunks (chapter_section);
