-- Migration 002: Add document_type, generated_artifacts title/status, and Question Paper tables

-- 1. Add document_type to documents table
ALTER TABLE documents ADD COLUMN IF NOT EXISTS document_type VARCHAR(50) DEFAULT 'STUDY_MATERIAL' NOT NULL;

-- 2. Add title and status to generated_artifacts table
ALTER TABLE generated_artifacts ADD COLUMN IF NOT EXISTS title VARCHAR(255);
ALTER TABLE generated_artifacts ADD COLUMN IF NOT EXISTS status VARCHAR(50) DEFAULT 'ACTIVE';

-- 3. Create question_paper_questions table if not exists
CREATE TABLE IF NOT EXISTS question_paper_questions (
    id VARCHAR(36) PRIMARY KEY,
    document_id VARCHAR(36) NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    question_number VARCHAR(32),
    question_text TEXT NOT NULL,
    section VARCHAR(128),
    marks DOUBLE PRECISION,
    source_page INTEGER,
    topics JSONB DEFAULT '[]'::jsonb,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS ix_question_paper_questions_doc_id ON question_paper_questions(document_id);

-- 4. Create question_support_analysis table if not exists
CREATE TABLE IF NOT EXISTS question_support_analysis (
    id VARCHAR(36) PRIMARY KEY,
    question_id VARCHAR(36) NOT NULL REFERENCES question_paper_questions(id) ON DELETE CASCADE,
    study_material_id VARCHAR(36) NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    status VARCHAR(50) NOT NULL,
    confidence DOUBLE PRECISION DEFAULT 1.0,
    source_pages JSONB DEFAULT '[]'::jsonb,
    source_chunk_ids JSONB DEFAULT '[]'::jsonb,
    evidence_summary TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS ix_question_support_analysis_q_id ON question_support_analysis(question_id);
CREATE INDEX IF NOT EXISTS ix_question_support_analysis_mat_id ON question_support_analysis(study_material_id);
