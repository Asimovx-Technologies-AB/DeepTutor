-- Ensure session_documents has all required columns and indexes for production
ALTER TABLE session_documents ADD COLUMN IF NOT EXISTS id UUID DEFAULT gen_random_uuid();
ALTER TABLE session_documents ADD COLUMN IF NOT EXISTS filename TEXT DEFAULT '';
ALTER TABLE session_documents ADD COLUMN IF NOT EXISTS file_path TEXT DEFAULT '';
ALTER TABLE session_documents ADD COLUMN IF NOT EXISTS status TEXT DEFAULT 'completed';
ALTER TABLE session_documents ADD COLUMN IF NOT EXISTS page_count INT DEFAULT 0;
ALTER TABLE session_documents ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ DEFAULT now();
ALTER TABLE session_documents ADD COLUMN IF NOT EXISTS uploaded_at TEXT DEFAULT '';

-- Backfill default values for existing rows
UPDATE session_documents SET filename = '' WHERE filename IS NULL;
UPDATE session_documents SET file_path = '' WHERE file_path IS NULL;
UPDATE session_documents SET status = 'completed' WHERE status IS NULL;
UPDATE session_documents SET page_count = 0 WHERE page_count IS NULL;

-- Ensure indexes exist for performance and conflict handling
CREATE UNIQUE INDEX IF NOT EXISTS ix_session_documents_id
    ON session_documents (id);

CREATE INDEX IF NOT EXISTS ix_session_documents_session_id
    ON session_documents (session_id);

CREATE INDEX IF NOT EXISTS ix_session_documents_user_id
    ON session_documents (user_id);
