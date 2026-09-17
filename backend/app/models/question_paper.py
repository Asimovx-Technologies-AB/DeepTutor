import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, Integer, Float, Text, DateTime, ForeignKey, JSON
from sqlalchemy.orm import relationship
from app.core.database import Base

def generate_uuid() -> str:
    return str(uuid.uuid4())

class QuestionPaperQuestion(Base):
    """
    Stores extracted questions from a Question Paper document.
    """
    __tablename__ = "question_paper_questions"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    document_id = Column(String(36), ForeignKey("documents.id", ondelete="CASCADE"), index=True, nullable=False)
    
    question_number = Column(String(32), nullable=True) # e.g. "1", "1a", "Q2"
    question_text = Column(Text, nullable=False)
    section = Column(String(128), nullable=True)
    marks = Column(Float, nullable=True)
    
    source_page = Column(Integer, nullable=True)
    topics = Column(JSON, default=list, nullable=True) # Extracted topics testing by this question
    
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

class QuestionSupportAnalysis(Base):
    """
    Stores semantic analysis of whether a Question Paper question is supported by a specific Study Material.
    """
    __tablename__ = "question_support_analysis"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    question_id = Column(String(36), ForeignKey("question_paper_questions.id", ondelete="CASCADE"), index=True, nullable=False)
    study_material_id = Column(String(36), ForeignKey("documents.id", ondelete="CASCADE"), index=True, nullable=False)
    
    status = Column(String(50), nullable=False) # SUPPORTED, PARTIALLY_SUPPORTED, NOT_SUPPORTED, AMBIGUOUS
    confidence = Column(Float, default=1.0)
    
    source_pages = Column(JSON, default=list, nullable=True)
    source_chunk_ids = Column(JSON, default=list, nullable=True)
    evidence_summary = Column(Text, nullable=True)
    
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
