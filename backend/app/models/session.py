import uuid
from datetime import datetime, timezone
from sqlalchemy import (
    Column, String, Integer, Float, Text, DateTime, ForeignKey, Index, JSON, Boolean
)
from sqlalchemy.orm import relationship
from app.core.database import Base


def generate_uuid() -> str:
    return str(uuid.uuid4())


class StudySession(Base):
    """
    Study Session Model representing an interactive learning room
    connected to an uploaded document and curriculum.
    """
    __tablename__ = "study_sessions"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    user_id = Column(String(36), default="default_user", index=True)
    document_id = Column(String(36), ForeignKey("documents.id", ondelete="SET NULL"), nullable=True, index=True)
    
    subject = Column(String(128), default="General Studies", nullable=False)
    title = Column(String(255), default="Study Session", nullable=False)
    document_name = Column(String(255), nullable=True)
    status = Column(String(50), default="active") # active, completed, archived
    
    topic_count = Column(Integer, default=0)
    message_count = Column(Integer, default=0)
    
    session_metadata = Column(JSON, default=dict, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    last_active = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # Relationships
    document = relationship("Document")
    curriculum_topics = relationship("CurriculumTopic", back_populates="session", cascade="all, delete-orphan")
    messages = relationship("ChatMessage", back_populates="session", cascade="all, delete-orphan")
    generated_artifacts = relationship("GeneratedArtifact", back_populates="session", cascade="all, delete-orphan")


class CurriculumTopic(Base):
    """
    Curriculum Topic Model representing a structured lesson module
    derived from the document's structure tree for the Learn Page.
    """
    __tablename__ = "curriculum_topics"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    session_id = Column(String(36), ForeignKey("study_sessions.id", ondelete="CASCADE"), index=True, nullable=False)
    document_id = Column(String(36), ForeignKey("documents.id", ondelete="CASCADE"), nullable=True)
    
    title = Column(String(255), nullable=False)
    summary = Column(Text, nullable=True)
    difficulty = Column(String(32), default="Intermediate") # Beginner, Intermediate, Advanced
    estimated_study_time = Column(String(64), default="15 mins")
    order_index = Column(Integer, default=0)
    
    key_concepts = Column(JSON, default=list, nullable=True) # List of concept strings
    structural_path = Column(String(255), nullable=True) # e.g. "Chapter 1 > Section 1.2"
    page_start = Column(Integer, default=1)
    page_end = Column(Integer, default=1)
    
    mastered = Column(Boolean, default=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    session = relationship("StudySession", back_populates="curriculum_topics")


class ChatMessage(Base):
    """
    Chat Message Model storing multi-turn conversations, citations,
    grounding metrics, and intent analysis.
    """
    __tablename__ = "chat_messages"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    session_id = Column(String(36), ForeignKey("study_sessions.id", ondelete="CASCADE"), index=True, nullable=False)
    topic_id = Column(String(36), ForeignKey("curriculum_topics.id", ondelete="SET NULL"), nullable=True)
    
    role = Column(String(20), nullable=False) # "user" or "assistant"
    content = Column(Text, nullable=False)
    
    # Provenance & Grounding Verification
    intent = Column(String(50), nullable=True)
    citations = Column(JSON, default=list, nullable=True) # List of source chunks and page numbers
    grounding_score = Column(Float, default=1.0)
    latency_ms = Column(Float, default=0.0)
    
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    session = relationship("StudySession", back_populates="messages")


class StudentProfile(Base):
    """
    Student Knowledge Profile Model.
    Tracks learning goals, difficulty preference, and overall mastery.
    """
    __tablename__ = "student_profiles"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    user_id = Column(String(36), unique=True, index=True, nullable=False)
    
    preferred_difficulty = Column(String(32), default="Intermediate")
    learning_goals = Column(JSON, default=list, nullable=True) # e.g. ["Exam Prep", "Concept Mastery"]
    mastery_summary = Column(JSON, default=dict, nullable=True)
    
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


class StudentMastery(Base):
    """
    Student Concept Mastery Model.
    Granular mastery score (0.0 - 1.0) per concept.
    """
    __tablename__ = "student_mastery"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    user_id = Column(String(36), index=True, nullable=False)
    concept = Column(String(128), index=True, nullable=False)
    
    mastery_score = Column(Float, default=0.5) # 0.0 to 1.0
    practice_attempts = Column(Integer, default=0)
    successful_attempts = Column(Integer, default=0)
    
    last_practiced = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        Index("ix_student_concept_unique", "user_id", "concept", unique=True),
    )
