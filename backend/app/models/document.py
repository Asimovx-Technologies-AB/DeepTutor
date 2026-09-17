import uuid
from datetime import datetime, timezone
from sqlalchemy import (
    Column, String, Integer, Float, Text, DateTime, ForeignKey, Index, JSON
)
from sqlalchemy.orm import relationship
from app.core.database import Base, is_sqlite

# Conditional import for pgvector
if not is_sqlite:
    try:
        from pgvector.sqlalchemy import Vector
    except ImportError:
        Vector = None
else:
    Vector = None


def generate_uuid() -> str:
    return str(uuid.uuid4())


class Document(Base):
    """Document Metadata Table."""
    __tablename__ = "documents"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    file_hash = Column(String(64), unique=True, index=True, nullable=False) # SHA-256
    filename = Column(String(255), nullable=False)
    file_path = Column(String(512), nullable=False)
    file_size_bytes = Column(Integer, nullable=False)
    mime_type = Column(String(100), default="application/pdf")
    document_type = Column(String(50), default="STUDY_MATERIAL") # STUDY_MATERIAL, QUESTION_PAPER
    page_count = Column(Integer, default=0)
    
    # Metadata extracted from PDF / Doc
    title = Column(String(512), nullable=True)
    author = Column(String(255), nullable=True)
    creation_date = Column(DateTime, nullable=True)
    pdf_version = Column(String(32), nullable=True)
    
    # Pipeline Orchestration State
    status = Column(String(50), default="QUEUED", index=True) # QUEUED, PARSING, EXTRACTING, STRUCTURING, CHUNKING, VALIDATING, STORING, COMPLETED, FAILED
    current_stage = Column(String(50), nullable=True)
    error_message = Column(Text, nullable=True)
    
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # Relationships
    pages = relationship("DocumentPage", back_populates="document", cascade="all, delete-orphan")
    chunks = relationship("KnowledgeChunk", back_populates="document", cascade="all, delete-orphan")
    assets = relationship("DocumentAsset", back_populates="document", cascade="all, delete-orphan")
    logs = relationship("ProcessingLog", back_populates="document", cascade="all, delete-orphan")


class DocumentPage(Base):
    """Page & Layout Metadata Table."""
    __tablename__ = "document_pages"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    document_id = Column(String(36), ForeignKey("documents.id", ondelete="CASCADE"), index=True, nullable=False)
    page_number = Column(Integer, nullable=False) # 1-indexed
    width = Column(Float, nullable=False)
    height = Column(Float, nullable=False)
    dpi = Column(Integer, default=150)
    orientation = Column(Integer, default=0) # 0, 90, 180, 270
    
    # Classification & Quality Metrics
    classification = Column(String(50), default="digital") # digital, scanned, hybrid
    character_density = Column(Float, default=0.0)
    ocr_applied = Column(Integer, default=0) # 0 = false, 1 = true
    image_storage_path = Column(String(512), nullable=True)
    
    # Layout Blocks Structure (bounding boxes, margins, columns)
    layout_data = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    document = relationship("Document", back_populates="pages")

    __table_args__ = (
        Index("ix_doc_page_unique", "document_id", "page_number", unique=True),
    )
