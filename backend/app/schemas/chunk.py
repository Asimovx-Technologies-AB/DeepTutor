from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field, ConfigDict


class KnowledgeChunkBase(BaseModel):
    """
    14 Dimensions of a Knowledge Chunk as specified in the Architecture Blueprint:
    1. Content
    2. Type
    3. Topic
    4. Chapter / Section
    5. Prev / Next Chunk
    6. Parent / Child
    7. Related Concepts
    8. Keywords / Entities
    9. Formulas
    10. Examples
    11. Source URI
    12. Confidence
    13. Provenance
    14. Knowledge Relationship Metadata
    """
    # Dimension 1: Content
    content: str = Field(..., description="Semantic content with embedded LaTeX and Markdown")

    # Dimension 2: Type
    chunk_type: str = Field("text", description="Type: text, section_header, table, formula, definition, example, summary")

    # Dimension 3: Topic
    topic: Optional[str] = Field(None, description="Thematic topic or domain")

    # Dimension 4: Chapter / Section
    chapter_section: Optional[str] = Field(None, description="Hierarchical path string")

    # Dimension 5: Prev / Next Chunk
    prev_chunk_id: Optional[str] = Field(None, description="Sequential previous chunk UUID")
    next_chunk_id: Optional[str] = Field(None, description="Sequential next chunk UUID")

    # Dimension 6: Parent / Child
    parent_id: Optional[str] = Field(None, description="Hierarchical parent chunk UUID")
    child_ids: List[str] = Field(default_factory=list, description="Child chunk UUIDs")

    # Dimension 7: Related Concepts
    related_concepts: List[str] = Field(default_factory=list, description="Cross-concept tags")

    # Dimension 8: Keywords / Entities
    keywords_entities: List[str] = Field(default_factory=list, description="Key domain entities")

    # Dimension 9: Formulas
    formulas: List[str] = Field(default_factory=list, description="Extracted LaTeX expressions")

    # Dimension 10: Examples
    examples: List[str] = Field(default_factory=list, description="Examples or case studies")

    # Dimension 11: Source URI & Bounding Box
    source_uri: Optional[str] = Field(None, description="URI reference e.g. page=1&bbox=[x0,y0,x1,y1]")
    bbox_coordinates: Optional[List[float]] = Field(None, description="[x0, y0, x1, y1]")

    # Dimension 12: Confidence
    confidence: float = Field(1.0, ge=0.0, le=1.0, description="Confidence score")

    # Dimension 13: Provenance
    provenance: Dict[str, Any] = Field(default_factory=dict, description="Parser/model provenance metadata")

    # Dimension 14: Knowledge Relationship Metadata
    relationship_metadata: Dict[str, Any] = Field(default_factory=dict, description="Semantic edge semantics")


class KnowledgeChunkCreate(KnowledgeChunkBase):
    document_id: str
    page_number: int
    chunk_index: int
    search_text: Optional[str] = None
    embedding: Optional[List[float]] = None


class KnowledgeChunkRead(KnowledgeChunkBase):
    model_config = ConfigDict(from_attributes=True)

    id: str
    document_id: str
    page_number: int
    chunk_index: int
    search_text: Optional[str] = None
    has_embedding: bool = False
