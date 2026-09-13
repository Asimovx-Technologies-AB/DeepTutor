import uuid
from datetime import datetime, timezone
from sqlalchemy import (
    Column, String, Integer, Float, Text, DateTime, ForeignKey, Index, JSON
)
from sqlalchemy.orm import relationship
from app.core.database import Base


def generate_uuid() -> str:
    return str(uuid.uuid4())


class ProcessingLog(Base):
    """
    Provenance & Processing Logs table.
    Tracks every stage of the document lifecycle with timing and metrics.
    """
    __tablename__ = "processing_logs"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    document_id = Column(String(36), ForeignKey("documents.id", ondelete="CASCADE"), index=True, nullable=False)
    stage = Column(String(64), index=True, nullable=False) # e.g. "PDF_PARSER", "LAYOUT_ANALYSIS", "CHUNKER"
    status = Column(String(32), default="SUCCESS") # SUCCESS, WARNING, FAILED
    execution_time_ms = Column(Float, default=0.0)
    
    # Detailed telemetry and metrics (e.g. chunks_produced, tokens, quality_score)
    metrics = Column(JSON, default=dict, nullable=True)
    message = Column(Text, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    document = relationship("Document", back_populates="logs")

    __table_args__ = (
        Index("ix_log_doc_stage", "document_id", "stage"),
    )
