-- ============================================================================
-- DeepTutor Shared Unified Database Schema
-- Multi-tenant isolation by user_id and session_id
-- ============================================================================

PRAGMA foreign_keys = ON;

-- ----------------------------------------------------------------------------
-- 1. Users Table
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    username TEXT NOT NULL UNIQUE,
    email TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'student',
    is_premium BOOLEAN DEFAULT 0,
    plan TEXT DEFAULT 'free',
    current_streak INTEGER DEFAULT 0,
    longest_streak INTEGER DEFAULT 0,
    total_learning_hours REAL DEFAULT 0.0,
    last_active_date TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
CREATE INDEX IF NOT EXISTS idx_users_username ON users(username);

-- ----------------------------------------------------------------------------
-- 2. Sessions Table (Workspaces / Study Rooms)
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY,                       -- e.g. 'session_1788429908602'
    user_id TEXT,                              -- FK to users.id (nullable for guest/legacy)
    title TEXT NOT NULL,
    subject TEXT NOT NULL DEFAULT 'General Study',
    topics_count INTEGER DEFAULT 0,
    messages_count INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_active TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_sessions_user_id ON sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_sessions_last_active ON sessions(last_active DESC);

-- ----------------------------------------------------------------------------
-- 3. Messages Table (Conversation History)
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS messages (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    user_id TEXT,
    role TEXT NOT NULL,                        -- 'user' | 'assistant' | 'system'
    content TEXT,                              -- Message text/response
    thought_process TEXT,                      -- Chain-of-thought trace
    quiz_data_json TEXT,                       -- Embedded quiz JSON if generated
    topics_json TEXT,                          -- Topic pills JSON
    attachment_json TEXT,                      -- Attached file metadata JSON
    is_explanation BOOLEAN DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_messages_session_id ON messages(session_id);
CREATE INDEX IF NOT EXISTS idx_messages_user_id ON messages(user_id);
CREATE INDEX IF NOT EXISTS idx_messages_created_at ON messages(session_id, created_at ASC);

-- ----------------------------------------------------------------------------
-- 4. Topics Table (Curriculum Roadmap & Study Map)
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS topics (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    user_id TEXT,
    title TEXT NOT NULL,
    summary TEXT,
    difficulty TEXT DEFAULT 'Beginner',         -- 'Beginner' | 'Intermediate' | 'Advanced'
    key_concepts_json TEXT DEFAULT '[]',       -- JSON array of key concept strings
    estimated_study_time TEXT DEFAULT '15 mins',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_topics_session_id ON topics(session_id);
CREATE INDEX IF NOT EXISTS idx_topics_user_id ON topics(user_id);

-- ----------------------------------------------------------------------------
-- 5. Study Notes / Cheat Sheets (Markdown Reference Documents)
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS study_notes (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    session_id TEXT,
    topic_id TEXT,
    title TEXT NOT NULL,
    content_md TEXT NOT NULL,                  -- Full Markdown study notes
    key_takeaways_json TEXT DEFAULT '[]',      -- JSON array of key bullet takeaways
    exam_tips_json TEXT DEFAULT '[]',          -- JSON array of exam tips
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_study_notes_user_id ON study_notes(user_id);
CREATE INDEX IF NOT EXISTS idx_study_notes_session_id ON study_notes(session_id);

-- ----------------------------------------------------------------------------
-- 6. Quizzes Table (Auto-generated Question Sets)
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS quizzes (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    session_id TEXT,
    topic_id TEXT,
    title TEXT NOT NULL,
    questions_json TEXT NOT NULL,              -- JSON array of quiz question objects
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_quizzes_user_id ON quizzes(user_id);
CREATE INDEX IF NOT EXISTS idx_quizzes_session_id ON quizzes(session_id);

-- ----------------------------------------------------------------------------
-- 7. Quiz Results / Attempts
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS quiz_attempts (
    id TEXT PRIMARY KEY,
    quiz_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    session_id TEXT,
    score INTEGER NOT NULL DEFAULT 0,
    max_score INTEGER NOT NULL DEFAULT 0,
    percentage REAL NOT NULL DEFAULT 0.0,
    answers_json TEXT,                         -- Student submitted answers JSON
    breakdown_json TEXT,                       -- Rubric breakdown JSON
    completed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (quiz_id) REFERENCES quizzes(id) ON DELETE CASCADE,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_quiz_attempts_user_id ON quiz_attempts(user_id);
CREATE INDEX IF NOT EXISTS idx_quiz_attempts_session_id ON quiz_attempts(session_id);
CREATE INDEX IF NOT EXISTS idx_quiz_attempts_quiz_id ON quiz_attempts(quiz_id);

-- ----------------------------------------------------------------------------
-- 8. Flashcards Table (Spaced Repetition Flashcards)
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS flashcards (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    session_id TEXT,
    topic_id TEXT,
    front TEXT NOT NULL,
    back TEXT NOT NULL,
    box INTEGER DEFAULT 1,                     -- Leitner box (1-5)
    review_count INTEGER DEFAULT 0,
    next_review_date TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_flashcards_user_id ON flashcards(user_id);
CREATE INDEX IF NOT EXISTS idx_flashcards_session_id ON flashcards(session_id);

-- ----------------------------------------------------------------------------
-- 9. Q&A Bank / Doubts Resolved
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS qna_bank (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    user_id TEXT,
    question TEXT NOT NULL,
    answer TEXT NOT NULL,
    topic_title TEXT,
    context_sources_json TEXT DEFAULT '[]',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_qna_bank_session_id ON qna_bank(session_id);
CREATE INDEX IF NOT EXISTS idx_qna_bank_user_id ON qna_bank(user_id);
