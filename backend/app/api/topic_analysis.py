from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.topic_analysis import DocumentTopicAnalysis, ExtractedTopic
from app.schemas.topic_analysis import DocumentTopicAnalysisRead, TopicAnalysisStatus
from app.services.topic_analyzer import TopicAnalysisService

router = APIRouter(prefix="/topic-analysis", tags=["Topic Analysis"])

@router.post("/{document_id}", response_model=TopicAnalysisStatus)
def start_topic_analysis(
    document_id: str,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """
    Triggers the Important Topic Extraction and Analysis pipeline for a given document.
    Runs asynchronously in the background.
    """
    # Check if already running or completed
    existing = db.query(DocumentTopicAnalysis).filter(DocumentTopicAnalysis.document_id == document_id).first()
    if existing:
        if existing.status in ("PENDING", "PROCESSING"):
            return TopicAnalysisStatus(
                id=existing.id,
                document_id=existing.document_id,
                status=existing.status,
                total_topics=existing.total_topics,
                created_at=existing.created_at
            )
        else:
            # Re-run: delete old and restart
            db.delete(existing)
            db.commit()

    # We defer the heavy lifting to the background task to avoid blocking the HTTP request
    def _run_analysis(doc_id: str):
        # We need a fresh db session for the background task
        from app.core.database import SessionLocal
        bg_db = SessionLocal()
        try:
            TopicAnalysisService.analyze_document_topics(bg_db, doc_id)
        finally:
            bg_db.close()

    background_tasks.add_task(_run_analysis, document_id)
    
    # Return a temporary pending status
    return TopicAnalysisStatus(
        id="pending",
        document_id=document_id,
        status="PENDING",
        total_topics=0,
        created_at=__import__("datetime").datetime.now(__import__("datetime").timezone.utc)
    )

@router.get("/{document_id}", response_model=DocumentTopicAnalysisRead)
def get_topic_analysis(
    document_id: str,
    db: Session = Depends(get_db)
):
    """
    Retrieves the extracted topics and their importance scores for a document.
    """
    analysis = db.query(DocumentTopicAnalysis).filter(DocumentTopicAnalysis.document_id == document_id).first()
    if not analysis:
        raise HTTPException(status_code=404, detail="Topic analysis not found for this document.")
        
    return analysis
