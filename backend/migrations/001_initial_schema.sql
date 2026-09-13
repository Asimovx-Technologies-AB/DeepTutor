-- ==============================================================================
-- DeepTutor Advanced Data Processing & Storage Architecture Schema
-- Target: PostgreSQL with pgvector extension & GIN Full-Text Search
-- ==============================================================================

CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- 1. Document Metadata Table
CREATE TABLE IF NOT EXISTS documents (
    id VARCHAR(36) PRIMARY KEY,
    file_hash VARCHAR(64) UNIQUE NOT NULL,
    filename VARCHAR(255) NOT NULL,
    file_path VARCHAR(512) NOT NULL,
    file_size_bytes INTEGER NOT NULL,
    mime_type VARCHAR(100) DEFAULT 'application/pdf',
    page_count INTEGER DEFAULT 0,
    title VARCHAR(512),
    author VARCHAR(255),
    creation_date TIMESTAMP WITH TIME ZONE,
    pdf_version VARCHAR(32),
    status VARCHAR(50) DEFAULT 'QUEUED',
    current_stage VARCHAR(50),
    error_message TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS ix_documents_file_hash ON documents(file_hash);
CREATE INDEX IF NOT EXISTS ix_documents_status ON documents(status);

-- 2. Page & Layout Metadata Table
CREATE TABLE IF NOT EXISTS document_pages (
    id VARCHAR(36) PRIMARY KEY,
    document_id VARCHAR(36) NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    page_number INTEGER NOT NULL,
    width DOUBLE PRECISION NOT NULL,
    height DOUBLE PRECISION NOT NULL,
    dpi INTEGER DEFAULT 150,
    orientation INTEGER DEFAULT 0,
    classification VARCHAR(50) DEFAULT 'digital',
    character_density DOUBLE PRECISION DEFAULT 0.0,
    ocr_applied INTEGER DEFAULT 0,
    image_storage_path VARCHAR(512),
    layout_data JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_doc_page UNIQUE (document_id, page_number)
);

CREATE INDEX IF NOT EXISTS ix_doc_pages_doc_id ON document_pages(document_id);

-- 3. 14-Dimension Knowledge Chunks Table
CREATE TABLE IF NOT EXISTS knowledge_chunks (
    id VARCHAR(36) PRIMARY KEY,
    document_id VARCHAR(36) NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    page_number INTEGER NOT NULL,
    chunk_index INTEGER NOT NULL,
    
    -- 14 Dimensions
    content TEXT NOT NULL,
    chunk_type VARCHAR(50) DEFAULT 'text' NOT NULL,
    topic VARCHAR(255),
    chapter_section VARCHAR(255),
    prev_chunk_id VARCHAR(36),
    next_chunk_id VARCHAR(36),
    parent_id VARCHAR(36),
    child_ids JSONB DEFAULT '[]'::jsonb,
    related_concepts JSONB DEFAULT '[]'::jsonb,
    keywords_entities JSONB DEFAULT '[]'::jsonb,
    formulas JSONB DEFAULT '[]'::jsonb,
    examples JSONB DEFAULT '[]'::jsonb,
    source_uri VARCHAR(512),
    bbox_coordinates JSONB,
    confidence DOUBLE PRECISION DEFAULT 1.0,
    provenance JSONB DEFAULT '{}'::jsonb,
    relationship_metadata JSONB DEFAULT '{}'::jsonb,
    
    -- Search & Vector Semantic Index
    embedding vector(1536),
    search_text TEXT,
    tsv_content tsvector GENERATED ALWAYS AS (to_tsvector('english', coalesce(content, '') || ' ' || coalesce(search_text, ''))) STORED,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS ix_chunks_doc_idx ON knowledge_chunks(document_id, chunk_index);
CREATE INDEX IF NOT EXISTS ix_chunks_type_topic ON knowledge_chunks(chunk_type, topic);
CREATE INDEX IF NOT EXISTS ix_chunks_tsv ON knowledge_chunks USING GIN(tsv_content);
-- Vector HNSW cosine index
CREATE INDEX IF NOT EXISTS ix_chunks_embedding_hnsw ON knowledge_chunks USING hnsw (embedding vector_cosine_ops);

-- 4. Semantic Knowledge Relationships (Graph) Table
CREATE TABLE IF NOT EXISTS knowledge_relationships (
    id VARCHAR(36) PRIMARY KEY,
    document_id VARCHAR(36) NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    source_chunk_id VARCHAR(36) NOT NULL REFERENCES knowledge_chunks(id) ON DELETE CASCADE,
    target_chunk_id VARCHAR(36) NOT NULL REFERENCES knowledge_chunks(id) ON DELETE CASCADE,
    relation_type VARCHAR(64) NOT NULL,
    weight DOUBLE PRECISION DEFAULT 1.0,
    edge_metadata JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS ix_rel_source ON knowledge_relationships(source_chunk_id);
CREATE INDEX IF NOT EXISTS ix_rel_target ON knowledge_relationships(target_chunk_id);

-- 5. Tables & Formulas Visual Assets Table
CREATE TABLE IF NOT EXISTS document_assets (
    id VARCHAR(36) PRIMARY KEY,
    document_id VARCHAR(36) NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    page_number INTEGER NOT NULL,
    asset_type VARCHAR(32) NOT NULL,
    latex TEXT,
    markdown TEXT,
    html TEXT,
    raw_text TEXT,
    caption VARCHAR(512),
    bounding_box JSONB,
    image_storage_path VARCHAR(512),
    confidence DOUBLE PRECISION DEFAULT 1.0,
    extra_metadata JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS ix_assets_doc_type ON document_assets(document_id, asset_type);

-- 6. Provenance & Processing Logs Table
CREATE TABLE IF NOT EXISTS processing_logs (
    id VARCHAR(36) PRIMARY KEY,
    document_id VARCHAR(36) NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    stage VARCHAR(64) NOT NULL,
    status VARCHAR(32) DEFAULT 'SUCCESS',
    execution_time_ms DOUBLE PRECISION DEFAULT 0.0,
    metrics JSONB DEFAULT '{}'::jsonb,
    message TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS ix_logs_doc_stage ON processing_logs(document_id, stage);
