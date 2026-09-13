import uuid
from datetime import datetime, timezone
from sqlalchemy import (
    Column, String, Integer, Float, Text, DateTime, ForeignKey, Index, JSON
)
from sqlalchemy.orm import relationship
from app.core.database import Base


def generate_uuid() -> str:
    return str(uuid.uuid4())


class DocumentAsset(Base):
    """
    Extracted Visual & Mathematical Assets (Tables, Formulas, Figures).
    Stores LaTeX representations, Markdown/HTML tables, and visual crops.
    """
    __tablename__ = "document_assets"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    document_id = Column(String(36), ForeignKey("documents.id", ondelete="CASCADE"), index=True, nullable=False)
    page_number = Column(Integer, nullable=False, index=True)
    
    # Asset type: "table", "formula", "figure"
    asset_type = Column(String(32), index=True, nullable=False)
    
    # Content representation
    latex = Column(Text, nullable=True) # Normalized LaTeX for formulas and mathematical tables
    markdown = Column(Text, nullable=True) # Markdown format for tables
    html = Column(Text, nullable=True) # HTML format for complex tables
    raw_text = Column(Text, nullable=True)
    caption = Column(String(512), nullable=True)
    
    # Location & Visual Assets
    bounding_box = Column(JSON, nullable=True) # [x0, y0, x1, y1]
    image_storage_path = Column(String(512), nullable=True)
    confidence = Column(Float, default=1.0)
    
    extra_metadata = Column(JSON, default=dict, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    document = relationship("Document", back_populates="assets")

    __table_args__ = (
        Index("ix_asset_doc_type", "document_id", "asset_type"),
    )
