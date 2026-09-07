-- Migration 002: Study sessions, lecture tracking, and student episodic memory schema
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- 1. Persisted Conversation Messages
CREATE TABLE IF NOT EXISTS study_session_messages (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id      TEXT NOT NULL,
    user_id         TEXT,
    role            TEXT NOT NULL,
    text            TEXT,
    thought_process TEXT,
    quiz_data_json  JSONB,
    topics_json     JSONB,
    attachment_json JSONB,
    is_explanation  BOOLEAN DEFAULT FALSE,
    created_at      TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_study_session_messages_session_id
    ON study_session_messages (session_id);

CREATE INDEX IF NOT EXISTS ix_study_session_messages_user_id
    ON study_session_messages (user_id);

CREATE INDEX IF NOT EXISTS ix_study_session_messages_created_at
    ON study_session_messages (created_at);

-- 2. Persisted Extracted Curriculum Topics
CREATE TABLE IF NOT EXISTS study_session_topics (
    id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id            TEXT NOT NULL,
    user_id               TEXT,
    title                 TEXT,
    summary               TEXT,
    difficulty            TEXT,
    key_concepts_json     JSONB DEFAULT '[]'::jsonb,
    estimated_study_time  TEXT,
    document_name         TEXT DEFAULT '',
    created_at            TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_study_session_topics_session_id
    ON study_session_topics (session_id);

CREATE INDEX IF NOT EXISTS ix_study_session_topics_user_id
    ON study_session_topics (user_id);

-- 3. Persisted Ingested Documents
CREATE TABLE IF NOT EXISTS session_documents (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id      TEXT NOT NULL,
    doc_hash        TEXT DEFAULT '',
    user_id         TEXT,
    filename        TEXT DEFAULT '',
    file_path       TEXT DEFAULT '',
    status          TEXT DEFAULT 'completed',
    page_count      INT DEFAULT 0,
    created_at      TIMESTAMPTZ DEFAULT now()
);

-- Ensure all columns exist if session_documents was pre-created
ALTER TABLE session_documents ADD COLUMN IF NOT EXISTS id UUID DEFAULT gen_random_uuid();
ALTER TABLE session_documents ADD COLUMN IF NOT EXISTS filename TEXT DEFAULT '';
ALTER TABLE session_documents ADD COLUMN IF NOT EXISTS file_path TEXT DEFAULT '';
ALTER TABLE session_documents ADD COLUMN IF NOT EXISTS status TEXT DEFAULT 'completed';
ALTER TABLE session_documents ADD COLUMN IF NOT EXISTS page_count INT DEFAULT 0;
ALTER TABLE session_documents ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ DEFAULT now();
CREATE UNIQUE INDEX IF NOT EXISTS ix_session_documents_id
    ON session_documents (id);

CREATE INDEX IF NOT EXISTS ix_session_documents_session_id
    ON session_documents (session_id);

CREATE INDEX IF NOT EXISTS ix_session_documents_user_id
    ON session_documents (user_id);

-- 4. Teacher Mode: Lecture Sessions
CREATE TABLE IF NOT EXISTS lecture_sessions (
    id                          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id                  TEXT NOT NULL,
    topic_id                    TEXT NOT NULL,
    topic_title                 TEXT NOT NULL,
    status                      TEXT NOT NULL DEFAULT 'diagnostic',
    diagnostic_question         TEXT,
    diagnostic_answer           TEXT,
    diagnostic_level            TEXT DEFAULT 'standard',
    current_phase               TEXT DEFAULT 'phase_1',
    current_segment_index       INT DEFAULT 0,
    accumulated_notes_markdown  TEXT DEFAULT '',
    teach_back_prompt           TEXT,
    teach_back_submission       TEXT,
    teach_back_grade_json       JSONB,
    created_at                  TIMESTAMPTZ DEFAULT now(),
    updated_at                  TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_lecture_sessions_session_topic
    ON lecture_sessions (session_id, topic_id);

-- 5. Teacher Mode: Checkpoints
CREATE TABLE IF NOT EXISTS lecture_checkpoints (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id        TEXT NOT NULL DEFAULT '',
    lecture_id        TEXT NOT NULL,
    phase             TEXT NOT NULL,
    question_prompt   TEXT NOT NULL,
    options_json      JSONB,
    correct_answer    TEXT NOT NULL,
    student_response  TEXT,
    is_correct        BOOLEAN,
    remedial_modality TEXT,
    remedial_content  TEXT,
    created_at        TIMESTAMPTZ DEFAULT now()
);

ALTER TABLE lecture_checkpoints ADD COLUMN IF NOT EXISTS session_id TEXT NOT NULL DEFAULT '';
ALTER TABLE lecture_checkpoints ALTER COLUMN is_correct TYPE BOOLEAN USING (CASE WHEN is_correct IS NULL THEN NULL WHEN is_correct::text = '0' THEN FALSE ELSE TRUE END);

CREATE INDEX IF NOT EXISTS ix_lecture_checkpoints_lecture_id
    ON lecture_checkpoints (lecture_id);

CREATE INDEX IF NOT EXISTS ix_lecture_checkpoints_session_id
    ON lecture_checkpoints (session_id);

-- 6. Teacher Mode: Pause & Ask Events
CREATE TABLE IF NOT EXISTS lecture_pause_events (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id       TEXT NOT NULL DEFAULT '',
    lecture_id       TEXT NOT NULL,
    phase            TEXT NOT NULL,
    token_offset     INT DEFAULT 0,
    student_question TEXT NOT NULL,
    teacher_response TEXT NOT NULL,
    created_at       TIMESTAMPTZ DEFAULT now()
);

ALTER TABLE lecture_pause_events ADD COLUMN IF NOT EXISTS session_id TEXT NOT NULL DEFAULT '';

CREATE INDEX IF NOT EXISTS ix_lecture_pause_events_lecture_id
    ON lecture_pause_events (lecture_id);

CREATE INDEX IF NOT EXISTS ix_lecture_pause_events_session_id
    ON lecture_pause_events (session_id);

-- 7. Teacher Mode: Mastered Topics Registry
CREATE TABLE IF NOT EXISTS user_mastered_topics (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id    TEXT DEFAULT '',
    user_id       TEXT,
    topic_title   TEXT NOT NULL,
    subject       TEXT NOT NULL,
    mastery_score REAL DEFAULT 0.0,
    lecture_id    TEXT,
    completed_at  TIMESTAMPTZ DEFAULT now()
);

-- Ensure user_id column exists if table pre-existed
ALTER TABLE user_mastered_topics ADD COLUMN IF NOT EXISTS user_id TEXT;

CREATE INDEX IF NOT EXISTS ix_user_mastered_topics_user_id
    ON user_mastered_topics (user_id);

CREATE INDEX IF NOT EXISTS ix_user_mastered_topics_session_id
    ON user_mastered_topics (session_id);

-- 8. Long-term User Episodic Memory
CREATE TABLE IF NOT EXISTS user_memory (
    user_id     TEXT PRIMARY KEY,
    memory_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    updated_at  TIMESTAMPTZ DEFAULT now()
);
