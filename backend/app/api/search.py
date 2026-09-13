from typing import List
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.schemas.pipeline import HybridSearchQuery, HybridSearchResult
from app.services.search_service import HybridSearchService

router = APIRouter(prefix="/search", tags=["Search"])


@router.post("", response_model=List[HybridSearchResult])
def search_knowledge_base(
    query: HybridSearchQuery,
    db: Session = Depends(get_db)
):
    """
    Executes Hybrid Search combining Full-Text (tsvector/BM25), Vector Semantic (pgvector),
    and Knowledge Graph traversal, fused with Reciprocal Rank Fusion (RRF) and
    verified with cross-modal hybrid consistency checks.
    """
    results = HybridSearchService.execute_search(session=db, query=query)
    return results
