"""
Pipeline Data Models for the Advanced Document Processing Pipeline.

Defines all shared data structures used across pipeline stages:
- PipelineDocument: top-level document envelope
- PipelineStatus: processing stage enum
- KnowledgeBoxType: the 17 semantic chunk categories
- KnowledgeChunk: enriched chunk with full metadata
- CanonicalDocument: validated output ready for storage
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple


# ─── Pipeline Status ─────────────────────────────────────────────────────────


class PipelineStatus(str, Enum):
    """Processing stage of a document in the pipeline."""

    RECEIVED = "received"
    CLASSIFYING = "classifying"
    EXTRACTING_TEXT = "extracting_text"
    EXTRACTING_VISUALS = "extracting_visuals"
    TILING = "tiling"
    VALIDATING = "validating"
    STORING = "storing"
    COMPLETED = "completed"
    ERROR = "error"


# ─── Knowledge Box Types ─────────────────────────────────────────────────────


class KnowledgeBoxType(str, Enum):
    """
    The 17 semantic knowledge box categories that every chunk is classified
    into by the Knowledge Tiler.  These drive downstream retrieval weighting,
    quiz generation, and teaching engine formatting.
    """

    PARAGRAPH = "paragraph"          # General prose / body text
    DEFINITION = "definition"        # Formal definitions ("X is defined as…")
    CONCEPT = "concept"              # Core concept descriptions
    HEADING = "heading"              # Section / chapter headings
    EXAMPLE = "example"              # Worked examples and illustrations
    EXPLANATION = "explanation"      # Detailed explanatory passages
    PROCEDURE = "procedure"          # Step-by-step processes / algorithms
    FORMULA = "formula"              # Standalone mathematical formulas
    THEOREM = "theorem"              # Named theorems, lemmas, corollaries
    PROOF = "proof"                  # Mathematical proofs
    TABLE = "table"                  # Tabular data (markdown tables)
    FIGURE = "figure"                # Figures, photos, illustrations
    DIAGRAM = "diagram"              # Technical diagrams, flowcharts, charts
    NOTE = "note"                    # Author notes, remarks, asides
    WARNING = "warning"              # Caution/warning blocks
    QUESTION = "question"            # End-of-chapter / inline questions
    EXERCISE = "exercise"            # Practice problems and exercises


# Mapping from knowledge box type to default retrieval weight.
# Higher weight = more likely to surface in retrieval results.
KNOWLEDGE_BOX_WEIGHTS: Dict[KnowledgeBoxType, float] = {
    KnowledgeBoxType.PARAGRAPH: 0.7,
    KnowledgeBoxType.DEFINITION: 1.5,
    KnowledgeBoxType.CONCEPT: 1.4,
    KnowledgeBoxType.HEADING: 0.3,
    KnowledgeBoxType.EXAMPLE: 1.3,
    KnowledgeBoxType.EXPLANATION: 1.2,
    KnowledgeBoxType.PROCEDURE: 1.3,
    KnowledgeBoxType.FORMULA: 1.4,
    KnowledgeBoxType.THEOREM: 1.5,
    KnowledgeBoxType.PROOF: 1.1,
    KnowledgeBoxType.TABLE: 1.2,
    KnowledgeBoxType.FIGURE: 1.0,
    KnowledgeBoxType.DIAGRAM: 1.0,
    KnowledgeBoxType.NOTE: 0.6,
    KnowledgeBoxType.WARNING: 0.8,
    KnowledgeBoxType.QUESTION: 1.1,
    KnowledgeBoxType.EXERCISE: 1.2,
}

# Confidence defaults by extraction method.
EXTRACTION_CONFIDENCE: Dict[str, float] = {
    "digital_text": 0.95,
    "vlm_ocr": 0.70,
    "pdfplumber_table": 0.85,
    "vlm_figure_caption": 0.60,
    "vlm_equation_latex": 0.65,
    "regex_equation": 0.90,
    "heading_regex": 0.92,
}


# ─── Extraction-stage data models ────────────────────────────────────────────


@dataclass
class FigureData:
    """A single figure/diagram extracted from a page."""

    page_num: int
    image_index: int
    image_bytes: bytes
    caption: str = ""
    bounding_box: Optional[Tuple[float, float, float, float]] = None
    mime_type: str = "image/png"


@dataclass
class TableData:
    """A single table extracted from a page."""

    page_num: int
    table_index: int
    title: str = ""
    headers: List[str] = field(default_factory=list)
    rows: List[List[str]] = field(default_factory=list)
    markdown: str = ""
    row_count: int = 0
    col_count: int = 0


@dataclass
class EquationData:
    """A single mathematical equation detected on a page."""

    page_num: int
    raw_text: str = ""
    latex: str = ""
    is_display: bool = False  # True = block display $$…$$, False = inline $…$
    context_text: str = ""    # Surrounding text for context


@dataclass
class PageContent:
    """Extraction results for a single page."""

    page_num: int
    raw_text: str = ""
    classification: str = "text"  # "text", "visual", "mixed"
    quality_score: float = 1.0    # 0.0–1.0
    figures: List[FigureData] = field(default_factory=list)
    tables: List[TableData] = field(default_factory=list)
    equations: List[EquationData] = field(default_factory=list)
    extraction_method: str = "digital_text"


# ─── Pipeline Document ───────────────────────────────────────────────────────


@dataclass
class PipelineDocument:
    """Top-level document envelope flowing through the pipeline."""

    doc_id: str
    file_path: str
    file_name: str
    file_type: str = "pdf"       # "pdf", "docx", "pptx", "image", "text"
    session_id: str = ""
    user_id: Optional[str] = None
    subject: str = "General"
    status: PipelineStatus = PipelineStatus.RECEIVED
    page_count: int = 0
    doc_hash: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.utcnow)
    error_message: Optional[str] = None

    # Populated during extraction
    pages: List[PageContent] = field(default_factory=list)


# ─── Knowledge Chunk ─────────────────────────────────────────────────────────


@dataclass
class KnowledgeChunk:
    """
    A single semantically-enriched chunk produced by the Knowledge Tiler.

    Every chunk is classified into one of the 17 KnowledgeBoxType categories,
    and carries rich metadata for downstream retrieval, quiz generation, and
    analytics.
    """

    chunk_id: str
    doc_id: str
    content: str

    # Knowledge box classification
    knowledge_box: KnowledgeBoxType = KnowledgeBoxType.PARAGRAPH

    # Structural metadata
    topic: str = ""
    chapter_section: str = ""       # "Ch 3 > 3.2 Photosynthesis"
    page: int = 1
    bounding_box: Optional[str] = None

    # Hierarchy
    parent_chunk_id: Optional[str] = None
    child_chunk_ids: List[str] = field(default_factory=list)

    # Semantic metadata
    named_concepts: List[str] = field(default_factory=list)

    # Quality & provenance
    confidence: float = 0.0
    templates: str = ""
    provenance: Dict[str, Any] = field(default_factory=dict)
    weight: float = 1.0

    # Legacy compatibility field (maps to source_type in existing schema)
    @property
    def source_type(self) -> str:
        """Maps knowledge box type to legacy source_type for backward compat."""
        _mapping = {
            KnowledgeBoxType.TABLE: "table",
            KnowledgeBoxType.FIGURE: "image_caption",
            KnowledgeBoxType.DIAGRAM: "image_caption",
            KnowledgeBoxType.FORMULA: "text",
        }
        return _mapping.get(self.knowledge_box, "text")


# ─── Document Intelligence ────────────────────────────────────────────────────


@dataclass
class DocumentIntelligence:
    """Aggregated analytics and quality metrics for a processed document."""

    total_pages: int = 0
    indexed_pages: int = 0
    coverage_pct: float = 0.0

    # Chunk counts by knowledge box type
    chunk_counts: Dict[str, int] = field(default_factory=dict)
    total_chunks: int = 0

    # Content classification
    detected_subject: str = ""
    is_study_material: bool = True
    content_category: str = "STUDY_MATERIAL"
    content_confidence: float = 0.0

    # Extraction quality
    extraction_errors: List[str] = field(default_factory=list)
    avg_confidence: float = 0.0

    # Named concept summary
    top_concepts: List[str] = field(default_factory=list)

    @property
    def table_chunks(self) -> int:
        return self.chunk_counts.get("table", 0)

    @property
    def figure_chunks(self) -> int:
        return self.chunk_counts.get("figure", 0) + self.chunk_counts.get("diagram", 0)

    @property
    def equation_chunks(self) -> int:
        return self.chunk_counts.get("formula", 0)

    @property
    def text_chunks(self) -> int:
        return self.total_chunks - self.table_chunks - self.figure_chunks


# ─── Canonical Document ──────────────────────────────────────────────────────


@dataclass
class CanonicalDocument:
    """
    Final validated output of the processing pipeline.
    Ready for indexing into all configured storage backends.
    """

    document: PipelineDocument
    chunks: List[KnowledgeChunk] = field(default_factory=list)
    intelligence: DocumentIntelligence = field(default_factory=DocumentIntelligence)

    @property
    def sample_text(self) -> str:
        """First 25000 chars of text-type chunks for topic extraction."""
        parts = []
        for chunk in self.chunks:
            if chunk.knowledge_box not in (
                KnowledgeBoxType.FIGURE,
                KnowledgeBoxType.DIAGRAM,
            ):
                parts.append(chunk.content)
            if sum(len(p) for p in parts) > 25000:
                break
        return "\n\n".join(parts)[:25000]
