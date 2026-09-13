import uuid
from datetime import datetime, timezone
from sqlalchemy import (
    Column, String, Integer, Float, Text, DateTime, ForeignKey, Index, JSON
)
from sqlalchemy.orm import relationship
from app.core.database import Base, is_sqlite, has_pgvector
from app.core.config import settings

# Conditional import for pgvector
if has_pgvector:
    try:
        from pgvector.sqlalchemy import Vector
    except ImportError:
        Vector = None
else:
    Vector = None


def generate_uuid() -> str:
    return str(uuid.uuid4())


class KnowledgeChunk(Base):
    """
    Knowledge Chunk Model representing the 14-dimension structured knowledge unit
    from the Advanced Document Processing & Storage Architecture.
    """
    __tablename__ = "knowledge_chunks"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    document_id = Column(String(36), ForeignKey("documents.id", ondelete="CASCADE"), index=True, nullable=False)
    page_number = Column(Integer, nullable=False, index=True)
    chunk_index = Column(Integer, nullable=False) # Sequential index within document

    # Dimension 1: Content
    content = Column(Text, nullable=False)

    # Dimension 2: Type (text, section_header, table, formula, definition, example, summary)
    chunk_type = Column(String(50), default="text", index=True, nullable=False)

    # Dimension 3: Topic
    topic = Column(String(255), index=True, nullable=True)

    # Dimension 4: Chapter / Section
    chapter_section = Column(String(255), index=True, nullable=True)

    # Dimension 5: Prev / Next Chunk Pointers
    prev_chunk_id = Column(String(36), nullable=True)
    next_chunk_id = Column(String(36), nullable=True)

    # Dimension 6: Parent / Child Hierarchical Structure
    parent_id = Column(String(36), nullable=True)
    child_ids = Column(JSON, default=list, nullable=True) # List of UUID strings

    # Dimension 7: Related Concepts
    related_concepts = Column(JSON, default=list, nullable=True) # List of concept strings

    # Dimension 8: Keywords / Entities
    keywords_entities = Column(JSON, default=list, nullable=True) # List of entity strings

    # Dimension 9: Formulas (LaTeX representations)
    formulas = Column(JSON, default=list, nullable=True) # List of LaTeX expressions

    # Dimension 10: Examples
    examples = Column(JSON, default=list, nullable=True) # List of examples

    # Dimension 11: Source URI / Bounding Box Coordinates
    source_uri = Column(String(512), nullable=True) # e.g. "page=3&bbox=[100,200,400,350]"
    bbox_coordinates = Column(JSON, nullable=True) # [x0, y0, x1, y1]

    # Dimension 12: Confidence Score
    confidence = Column(Float, default=1.0)

    # Dimension 13: Provenance (Parser origin, OCR model, timestamp)
    provenance = Column(JSON, default=dict, nullable=True)

    # Dimension 14: Knowledge Relationship Metadata (Graph semantics)
    relationship_metadata = Column(JSON, default=dict, nullable=True)

    # Vector Semantic Index Column
    if Vector is not None and not is_sqlite:
        embedding = Column(Vector(settings.EMBEDDING_DIMENSION), nullable=True)
    else:
        embedding = Column(JSON, nullable=True) # Fallback vector serialization

    # Search Vector representation
    search_text = Column(Text, nullable=True)

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    # Relationships
    document = relationship("Document", back_populates="chunks")

    __table_args__ = (
        Index("ix_chunk_doc_order", "document_id", "chunk_index"),
        Index("ix_chunk_type_topic", "chunk_type", "topic"),
    )
