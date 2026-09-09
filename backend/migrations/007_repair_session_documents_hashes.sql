-- 007_repair_session_documents_hashes.sql
-- Harmonize session_documents metadata and 64-character cryptographic content hashes

-- 1. Backfill filename, file_path, status, and page_count where doc_hash matches
UPDATE session_documents sd
SET filename = d.file_name,
    file_path = d.file_path,
    status = COALESCE(NULLIF(d.status, ''), 'completed'),
    page_count = COALESCE(d.chunk_count, 0)
FROM documents d
WHERE sd.doc_hash = d.doc_hash
  AND (sd.filename IS NULL OR sd.filename = '');

-- 2. Remove obsolete 32-character rows where a matching 64-character row already exists in the same session
DELETE FROM session_documents sd
WHERE LENGTH(sd.doc_hash) < 64
  AND EXISTS (
      SELECT 1 FROM session_documents sd2
      JOIN documents d ON d.doc_hash = sd2.doc_hash
      WHERE sd2.session_id = sd.session_id
        AND LENGTH(sd2.doc_hash) = 64
        AND (sd2.filename = sd.filename OR d.file_name = sd.filename)
  );

-- 3. Upgrade remaining 32-character rows to 64-character cryptographic content hash
UPDATE session_documents sd
SET doc_hash = d.doc_hash,
    file_path = COALESCE(NULLIF(sd.file_path, ''), d.file_path),
    status = COALESCE(NULLIF(sd.status, ''), d.status, 'completed'),
    page_count = COALESCE(NULLIF(sd.page_count, 0), d.chunk_count, 0)
FROM documents d
WHERE sd.session_id = d.topic_id
  AND sd.filename = d.file_name
  AND LENGTH(sd.doc_hash) < 64
  AND LENGTH(d.doc_hash) = 64;
