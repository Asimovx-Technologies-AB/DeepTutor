"""
Study Material Retrieval Layer
==============================
Pluggable retrieval interface and PostgreSQL/pgvector implementation to fetch
verified study chunks for flashcard/quiz generation.
"""

from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
import logging
from sqlalchemy.orm import Session
from sqlalchemy import or_

from app.models.document import Document
from app.models.chunk import KnowledgeChunk
from app.models.session import StudySession, CurriculumTopic

logger = logging.getLogger(__name__)


class BaseStudyMaterialRetriever(ABC):
    """Abstract interface for study material retrieval."""

    @abstractmethod
    def retrieve_chunks(
        self,
        topic: str,
        document_id: Optional[str] = None,
        session_id: Optional[str] = None,
        top_k: int = 5
    ) -> List[Dict[str, Any]]:
        """Retrieves top_k relevant text chunks for a given topic."""
        pass


class PostgresStudyMaterialRetriever(BaseStudyMaterialRetriever):
    """
    Concrete retriever querying PostgreSQL and pgvector for the student's
    verified document chunks.
    """

    def __init__(self, db: Session):
        self.db = db

    def _resolve_document(
        self,
        document_id: Optional[str] = None,
        session_id: Optional[str] = None
    ) -> Optional[Document]:
        """Finds the active study document in PostgreSQL."""
        if document_id:
            doc = self.db.query(Document).filter(Document.id == document_id).first()
            if doc:
                return doc

        if session_id:
            sess = self.db.query(StudySession).filter(StudySession.id == session_id).first()
            if sess and sess.document_id:
                doc = self.db.query(Document).filter(Document.id == sess.document_id).first()
                if doc:
                    return doc

        # Fallback to the latest processed document
        return self.db.query(Document).order_by(Document.created_at.desc()).first()

    def retrieve_chunks(
        self,
        topic: str,
        document_id: Optional[str] = None,
        session_id: Optional[str] = None,
        top_k: int = 5
    ) -> List[Dict[str, Any]]:
        doc = self._resolve_document(document_id, session_id)
        if not doc:
            logger.info("[Retriever] No document found in PostgreSQL.")
            return []

        doc_id = doc.id
        # Tokenize topic terms for keyword filtering
        terms = [t.strip().lower() for t in topic.split() if len(t.strip()) > 2]

        matched_chunks: List[KnowledgeChunk] = []
        if terms:
            conditions = [
                or_(
                    KnowledgeChunk.content.ilike(f"%{term}%"),
                    KnowledgeChunk.topic.ilike(f"%{term}%"),
                    KnowledgeChunk.chapter_section.ilike(f"%{term}%")
                )
                for term in terms[:4]
            ]
            matched_chunks = (
                self.db.query(KnowledgeChunk)
                .filter(KnowledgeChunk.document_id == doc_id, or_(*conditions))
                .limit(top_k)
                .all()
            )

        # If not enough chunks found by keyword, get general top chunks
        if len(matched_chunks) < top_k:
            existing_ids = {c.id for c in matched_chunks}
            fallback_chunks = (
                self.db.query(KnowledgeChunk)
                .filter(KnowledgeChunk.document_id == doc_id)
                .order_by(KnowledgeChunk.chunk_index.asc())
                .limit(top_k * 2)
                .all()
            )
            for c in fallback_chunks:
                if c.id not in existing_ids:
                    matched_chunks.append(c)
                if len(matched_chunks) >= top_k:
                    break

        results = []
        for c in matched_chunks:
            results.append({
                "id": c.id,
                "content": c.content,
                "topic": c.topic or topic,
                "chapter_section": c.chapter_section,
                "related_concepts": c.related_concepts or [],
                "page_number": c.page_number or 1,
                "document_title": doc.title or doc.filename or "Study Document"
            })

        return results
