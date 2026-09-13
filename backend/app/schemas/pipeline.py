from datetime import datetime
from typing import List, Optional, Dict, Any, Literal
from pydantic import BaseModel, Field
from app.schemas.chunk import KnowledgeChunkRead


class PipelineJobStatus(BaseModel):
    document_id: str
    filename: str
    status: str # QUEUED, PARSING, EXTRACTING, STRUCTURING, CHUNKING, VALIDATING, STORING, COMPLETED, FAILED
    current_stage: Optional[str] = None
    progress_percentage: float = 0.0
    error_message: Optional[str] = None
    stage_durations_ms: Dict[str, float] = Field(default_factory=dict)
    total_pages: int = 0
    total_chunks: int = 0
    total_assets: int = 0
    started_at: datetime
    completed_at: Optional[datetime] = None


class HybridSearchQuery(BaseModel):
    query: str = Field(..., min_length=1, description="Search query string")
    document_id: Optional[str] = Field(None, description="Optional document filter")
    top_k: int = Field(5, ge=1, le=50, description="Number of results to return")
    search_mode: Literal["hybrid", "vector_only", "full_text_only", "graph_only"] = "hybrid"
    
    # Weights for Reciprocal Rank Fusion (RRF)
    vector_weight: float = Field(0.5, ge=0.0, le=1.0)
    fts_weight: float = Field(0.3, ge=0.0, le=1.0)
    graph_weight: float = Field(0.2, ge=0.0, le=1.0)
    
    # Verification & Filtering
    chunk_type: Optional[str] = None
    min_confidence: float = Field(0.0, ge=0.0, le=1.0)
    enable_hybrid_checks: bool = Field(True, description="Perform cross-modal consistency checks")


class HybridVerificationCheck(BaseModel):
    """
    Validation check comparing Full-Text, Vector Semantic, and Graph traversal signals.
    Guarantees search precision and detects hallucinations or misaligned matches.
    """
    fts_matched: bool
    vector_matched: bool
    graph_connected: bool
    fts_score: float = 0.0
    vector_cosine_score: float = 0.0
    graph_hop_distance: int = -1
    concordance_score: float = Field(..., ge=0.0, le=1.0, description="Consensus ratio across search modalities")
    verification_status: Literal["VERIFIED", "PARTIAL", "WEAK"] = "PARTIAL"
    verification_notes: str = ""


class HybridSearchResult(BaseModel):
    chunk: KnowledgeChunkRead
    final_score: float
    rrf_rank: int
    verification: Optional[HybridVerificationCheck] = None
