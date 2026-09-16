import uuid
from datetime import datetime, timezone
from sqlalchemy import (
    Column, String, Integer, Float, Text, DateTime, ForeignKey, Index, JSON, Boolean
)
from sqlalchemy.orm import relationship
from app.core.database import Base


def generate_uuid() -> str:
    return str(uuid.uuid4())


class DocumentTopicAnalysis(Base):
    """
    Tracks the overall status and metadata of the topic importance analysis
    for a specific document.
    """
    __tablename__ = "document_topic_analysis"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    document_id = Column(String(36), ForeignKey("documents.id", ondelete="CASCADE"), index=True, nullable=False)
    
    analysis_version = Column(String(32), default="v1.0")
    status = Column(String(50), default="PENDING") # PENDING, PROCESSING, COMPLETED, FAILED
    total_topics = Column(Integer, default=0)
    
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    document = relationship("Document")
    extracted_topics = relationship("ExtractedTopic", back_populates="analysis", cascade="all, delete-orphan")


class ExtractedTopic(Base):
    """
    Represents a single extracted important topic from a document, 
    complete with calculated scores, hierarchy, and evidence signals.
    """
    __tablename__ = "extracted_topics"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    analysis_id = Column(String(36), ForeignKey("document_topic_analysis.id", ondelete="CASCADE"), index=True, nullable=False)
    
    # Topic Information
    topic = Column(String(255), nullable=False)
    chapter = Column(String(255), nullable=True) # e.g. "Chapter 3: Neural Networks"
    
    # Importance Scoring
    importance_score = Column(Float, default=0.0) # 0.0 to 1.0
    importance_level = Column(String(20), default="LOW") # HIGH, MEDIUM, LOW
    
    # Evidence / Signal Flags
    definitions_present = Column(Boolean, default=False)
    formula_present = Column(Boolean, default=False)
    examples_present = Column(Boolean, default=False)
    questions_present = Column(Boolean, default=False)
    summary_present = Column(Boolean, default=False)
    learning_objective_present = Column(Boolean, default=False)
    
    # Textual Evidence Snippets
    evidence = Column(JSON, default=list, nullable=True) # List of string explanations
    source_pages = Column(JSON, default=list, nullable=True) # List of ints
    
    # Knowledge Graph Relationships
    prerequisites = Column(JSON, default=list, nullable=True)
    related_topics = Column(JSON, default=list, nullable=True)
    subtopics = Column(JSON, default=list, nullable=True)
    
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    analysis = relationship("DocumentTopicAnalysis", back_populates="extracted_topics")

    __table_args__ = (
        Index("ix_topic_analysis_level", "analysis_id", "importance_level"),
    )
