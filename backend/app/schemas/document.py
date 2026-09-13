from datetime import datetime, timezone
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field, ConfigDict
from app.schemas.chunk import KnowledgeChunkRead
from app.schemas.layout import TableAsset, FormulaAsset, LayoutBlock


class DocumentMetadataRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    file_hash: str
    filename: str
    file_size_bytes: int
    mime_type: str
    page_count: int
    title: Optional[str] = None
    author: Optional[str] = None
    creation_date: Optional[datetime] = None
    pdf_version: Optional[str] = None
    status: str
    current_stage: Optional[str] = None
    error_message: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    key_topics: List[str] = Field(default_factory=list)
    detected_subject: Optional[str] = None
    session_count: int = 0
    linked_sessions: List[Dict[str, Any]] = Field(default_factory=list)
    file_name: Optional[str] = None
    file_type: Optional[str] = "PDF"
    doc_hash: Optional[str] = None
    indexed: bool = True
    index_status: Optional[str] = "done"


class StructuralNode(BaseModel):
    """Hierarchical node in the document structure tree."""
    id: str
    title: str
    level: int # 1 = Chapter, 2 = Section, 3 = Subsection, 4 = Paragraph
    path: str
    page_start: int
    page_end: int
    chunk_ids: List[str] = Field(default_factory=list)
    children: List["StructuralNode"] = Field(default_factory=list)


class RelationshipEdge(BaseModel):
    source_chunk_id: str
    target_chunk_id: str
    relation_type: str
    weight: float = 1.0
    edge_metadata: Dict[str, Any] = Field(default_factory=dict)


class PageLayoutInfo(BaseModel):
    page_number: int
    width: float
    height: float
    dpi: int = 150
    classification: str # digital, scanned, hybrid
    character_density: float
    blocks: List[LayoutBlock] = Field(default_factory=list)


class CanonicalDocumentRepresentation(BaseModel):
    """
    Canonical Document Representation:
    Unified data model synthesizing all extracted metadata, pages,
    hierarchical structure tree, knowledge chunks, assets, and relationship edges.
    """
    metadata: DocumentMetadataRead
    pages: List[PageLayoutInfo] = Field(default_factory=list)
    structure_tree: List[StructuralNode] = Field(default_factory=list)
    knowledge_chunks: List[KnowledgeChunkRead] = Field(default_factory=list)
    tables: List[TableAsset] = Field(default_factory=list)
    formulas: List[FormulaAsset] = Field(default_factory=list)
    relationships: List[RelationshipEdge] = Field(default_factory=list)
