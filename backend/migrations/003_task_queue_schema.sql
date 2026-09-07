-- 003_task_queue_schema.sql: Durable Asynchronous Task Queue for DeepTutor
-- Supports row-level leasing (FOR UPDATE SKIP LOCKED), retries, and failure tracking.
-- NOTE: pgcrypto is deliberately NOT created here. Azure Database for
-- PostgreSQL Flexible Server only permits extensions on its azure.extensions
-- allow-list (VECTOR, PG_TRGM, UUID-OSSP), so CREATE EXTENSION pgcrypto
-- aborts the whole migration transaction. PostgreSQL 13+ ships
-- gen_random_uuid() in core, which is all these tables need.


CREATE TABLE IF NOT EXISTS background_tasks (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    task_type     VARCHAR(64) NOT NULL,
    payload       JSONB NOT NULL DEFAULT '{}'::jsonb,
    status        VARCHAR(32) NOT NULL DEFAULT 'pending', -- pending, processing, completed, failed
    attempts      INT NOT NULL DEFAULT 0,
    max_attempts  INT NOT NULL DEFAULT 3,
    locked_until  TIMESTAMPTZ,
    last_error    TEXT,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_background_tasks_status_locked
    ON background_tasks (status, locked_until, created_at);

CREATE INDEX IF NOT EXISTS ix_background_tasks_task_type
    ON background_tasks (task_type);
