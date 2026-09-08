-- The dashboard and progress endpoints all read the Document ORM model, and
-- every one of them returned 500 in the deployed environment while /auth/login
-- kept working. 775fe08 added doc_hash, status, error_message and key_topics to
-- the model, but the only thing that ever added them to an existing table is the
-- ALTER block in app/core/database.py, which is guarded by
-- `engine.dialect.name == "sqlite"`. create_all() creates missing tables and
-- never alters existing ones, so on PostgreSQL the pre-775fe08 `documents` table
-- kept its old shape and SELECT documents.doc_hash failed with UndefinedColumn.
--
-- Column defaults match the model so existing rows read back as they would on a
-- freshly created table: key_topics is the JSON text "[]" that the key_topics
-- property json.loads(), not SQL NULL, which would otherwise take the except
-- branch on every row.
ALTER TABLE documents ADD COLUMN IF NOT EXISTS doc_hash VARCHAR(64);
ALTER TABLE documents ADD COLUMN IF NOT EXISTS status VARCHAR(20) DEFAULT 'pending';
ALTER TABLE documents ADD COLUMN IF NOT EXISTS error_message TEXT;
ALTER TABLE documents ADD COLUMN IF NOT EXISTS key_topics TEXT DEFAULT '[]';

-- Rows that predate the columns get the defaults too; ADD COLUMN only backfills
-- rows written after it on some versions when the default is added separately.
UPDATE documents SET status = 'pending' WHERE status IS NULL;
UPDATE documents SET key_topics = '[]' WHERE key_topics IS NULL;

-- The model declares index=True on doc_hash, which create_all would have built
-- alongside the column.
CREATE INDEX IF NOT EXISTS ix_documents_doc_hash ON documents (doc_hash);
