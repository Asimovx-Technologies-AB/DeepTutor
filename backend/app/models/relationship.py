import uuid
from datetime import datetime, timezone
from sqlalchemy import (
    Column, String, Float, DateTime, ForeignKey, Index, JSON
)
from app.core.database import Base


def generate_uuid() -> str:
    return str(uuid.uuid4())


class KnowledgeRelationship(Base):
    """
    Knowledge Graph Edges linking concepts, chunks, and sections.
    Enables semantic graph traversal and relational reasoning.
    """
    __tablename__ = "knowledge_relationships"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    document_id = Column(String(36), ForeignKey("documents.id", ondelete="CASCADE"), index=True, nullable=False)
    source_chunk_id = Column(String(36), ForeignKey("knowledge_chunks.id", ondelete="CASCADE"), index=True, nullable=False)
    target_chunk_id = Column(String(36), ForeignKey("knowledge_chunks.id", ondelete="CASCADE"), index=True, nullable=False)
    
    # Relation type: "prerequisite_of", "elaborates", "contrasts_with", "defines", "proves", "references"
    relation_type = Column(String(64), index=True, nullable=False)
    weight = Column(Float, default=1.0)
    
    # Metadata for relationship rationale and context
    edge_metadata = Column(JSON, default=dict, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        Index("ix_rel_source_target", "source_chunk_id", "target_chunk_id"),
    )
