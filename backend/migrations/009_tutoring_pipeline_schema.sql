-- Migration 009: Intelligent Tutoring System Schema
-- Persists curriculum knowledge maps, personalized study plans, and student concept mastery.

CREATE TABLE IF NOT EXISTS curriculum_knowledge_maps (
    course_id TEXT PRIMARY KEY,
    subject TEXT NOT NULL,
    title TEXT NOT NULL,
    topics JSONB NOT NULL DEFAULT '[]'::jsonb,
    dependency_graph JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_curriculum_knowledge_maps_subject
    ON curriculum_knowledge_maps (subject);

CREATE TABLE IF NOT EXISTS personalized_study_plans (
    plan_id TEXT PRIMARY KEY,
    student_id TEXT NOT NULL,
    course_id TEXT NOT NULL,
    sessions JSONB NOT NULL DEFAULT '[]'::jsonb,
    target_date TEXT DEFAULT '',
    is_exam_ready BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_personalized_study_plans_student
    ON personalized_study_plans (student_id);

CREATE INDEX IF NOT EXISTS ix_personalized_study_plans_course
    ON personalized_study_plans (course_id);

CREATE TABLE IF NOT EXISTS student_concept_mastery (
    user_id TEXT NOT NULL,
    concept_id TEXT NOT NULL,
    course_id TEXT NOT NULL DEFAULT '',
    mastery_score DOUBLE PRECISION NOT NULL DEFAULT 0.5,
    attempts_count INTEGER NOT NULL DEFAULT 0,
    success_count INTEGER NOT NULL DEFAULT 0,
    last_evaluated TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id, concept_id)
);

CREATE INDEX IF NOT EXISTS ix_student_concept_mastery_user_course
    ON student_concept_mastery (user_id, course_id);
