from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import or_
from app.core.database import get_db
from app.models.chunk import KnowledgeChunk
from app.models.relationship import KnowledgeRelationship
from app.schemas.chunk import KnowledgeChunkRead

router = APIRouter(prefix="/chunks", tags=["Chunks"])


@router.get("/{chunk_id}", response_model=KnowledgeChunkRead)
def get_chunk(
    chunk_id: str,
    db: Session = Depends(get_db)
):
    """Retrieves a single Knowledge Chunk by ID with all 14 dimensions."""
    chunk = db.query(KnowledgeChunk).filter(KnowledgeChunk.id == chunk_id).first()
    if not chunk:
        raise HTTPException(status_code=404, detail="Knowledge chunk not found.")
    return KnowledgeChunkRead.model_validate(chunk)


@router.get("/{chunk_id}/lineage")
def get_chunk_lineage(
    chunk_id: str,
    db: Session = Depends(get_db)
):
    """
    Retrieves sequential lineage (prev_chunk, current_chunk, next_chunk)
    and hierarchical lineage (parent, children).
    """
    chunk = db.query(KnowledgeChunk).filter(KnowledgeChunk.id == chunk_id).first()
    if not chunk:
        raise HTTPException(status_code=404, detail="Knowledge chunk not found.")

    prev_c = db.query(KnowledgeChunk).filter(KnowledgeChunk.id == chunk.prev_chunk_id).first() if chunk.prev_chunk_id else None
    next_c = db.query(KnowledgeChunk).filter(KnowledgeChunk.id == chunk.next_chunk_id).first() if chunk.next_chunk_id else None
    parent_c = db.query(KnowledgeChunk).filter(KnowledgeChunk.id == chunk.parent_id).first() if chunk.parent_id else None

    return {
        "current": KnowledgeChunkRead.model_validate(chunk),
        "previous": KnowledgeChunkRead.model_validate(prev_c) if prev_c else None,
        "next": KnowledgeChunkRead.model_validate(next_c) if next_c else None,
        "parent": KnowledgeChunkRead.model_validate(parent_c) if parent_c else None,
    }


@router.get("/{chunk_id}/relationships")
def get_chunk_relationships(
    chunk_id: str,
    db: Session = Depends(get_db)
):
    """Retrieves all semantic graph edges connected to this chunk."""
    rels = db.query(KnowledgeRelationship).filter(
        or_(
            KnowledgeRelationship.source_chunk_id == chunk_id,
            KnowledgeRelationship.target_chunk_id == chunk_id
        )
    ).all()

    return {
        "chunk_id": chunk_id,
        "relationships": [
            {
                "id": r.id,
                "source_chunk_id": r.source_chunk_id,
                "target_chunk_id": r.target_chunk_id,
                "relation_type": r.relation_type,
                "weight": r.weight,
                "metadata": r.edge_metadata,
            }
            for r in rels
        ]
    }
