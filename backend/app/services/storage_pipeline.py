import logging
from typing import List, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import text
from app.models.document import Document, DocumentPage
from app.models.chunk import KnowledgeChunk
from app.models.relationship import KnowledgeRelationship
from app.models.assets import DocumentAsset
from app.models.logs import ProcessingLog
from app.schemas.document import CanonicalDocumentRepresentation
from app.core.database import is_sqlite

logger = logging.getLogger(__name__)


class DataStoragePipeline:
    """
    Data Storage Pipeline.
    Persists all canonical representations across multi-table schema in PostgreSQL / pgvector:
    - Document Metadata
    - Page & Layout Metadata
    - 14-Dimension Knowledge Chunks
    - Semantic Knowledge Relationships (Graph)
    - Tables & Formulas Assets
    - Provenance & Processing Logs
    """

    @classmethod
    def persist_canonical_document(
        cls,
        session: Session,
        canonical_doc: CanonicalDocumentRepresentation,
        stage_durations: Dict[str, float] | None = None
    ) -> bool:
        doc_meta = canonical_doc.metadata
        doc_id = doc_meta.id

        try:
            # 1. Persist or Update Document Record
            db_doc = session.query(Document).filter(Document.id == doc_id).first()
            if not db_doc:
                db_doc = Document(
                    id=doc_id,
                    file_hash=doc_meta.file_hash,
                    filename=doc_meta.filename,
                    file_path=f"storage://{doc_meta.filename}",
                    file_size_bytes=doc_meta.file_size_bytes,
                    mime_type=doc_meta.mime_type,
                    page_count=doc_meta.page_count,
                    title=doc_meta.title,
                    author=doc_meta.author,
                    creation_date=doc_meta.creation_date,
                    pdf_version=doc_meta.pdf_version,
                    status="INDEXED",
                    current_stage="COMPLETED",
                )
                session.add(db_doc)
            else:
                db_doc.status = "INDEXED"
                db_doc.current_stage = "COMPLETED"
                db_doc.page_count = doc_meta.page_count
                db_doc.title = doc_meta.title
                # Cascading clean-up of prior child records to guarantee idempotency
                session.query(ProcessingLog).filter(ProcessingLog.document_id == doc_id).delete(synchronize_session=False)
                session.query(KnowledgeRelationship).filter(KnowledgeRelationship.document_id == doc_id).delete(synchronize_session=False)
                session.query(DocumentAsset).filter(DocumentAsset.document_id == doc_id).delete(synchronize_session=False)
                session.query(KnowledgeChunk).filter(KnowledgeChunk.document_id == doc_id).delete(synchronize_session=False)
                session.query(DocumentPage).filter(DocumentPage.document_id == doc_id).delete(synchronize_session=False)

            session.flush()

            # 2. Persist Page & Layout Metadata
            for i, p in enumerate(canonical_doc.pages):
                page_record = DocumentPage(
                    document_id=doc_id,
                    page_number=p.page_number,
                    width=p.width,
                    height=p.height,
                    dpi=p.dpi,
                    classification=p.classification,
                    character_density=p.character_density,
                    layout_data={"blocks_count": len(p.blocks)},
                )
                session.add(page_record)
                if (i + 1) % 25 == 0:
                    session.flush()

            session.flush()

            # 3. Persist Knowledge Chunks (14 Dimensions + Vector Embeddings)
            from app.services.embedding_service import default_embedding_service
            chunk_texts = [cd.content for cd in canonical_doc.knowledge_chunks]
            chunk_embs = default_embedding_service.embed_batch(chunk_texts) if chunk_texts else []

            for i, chunk_data in enumerate(canonical_doc.knowledge_chunks):
                emb = chunk_embs[i] if i < len(chunk_embs) else None
                if emb is not None:
                    emb = [float(x) for x in emb]

                chunk_record = KnowledgeChunk(
                    id=chunk_data.id,
                    document_id=doc_id,
                    page_number=chunk_data.page_number,
                    chunk_index=chunk_data.chunk_index,
                    content=chunk_data.content,
                    chunk_type=chunk_data.chunk_type or "text",
                    topic=chunk_data.topic,
                    chapter_section=chunk_data.chapter_section,
                    prev_chunk_id=chunk_data.prev_chunk_id,
                    next_chunk_id=chunk_data.next_chunk_id,
                    parent_id=chunk_data.parent_id,
                    child_ids=chunk_data.child_ids if chunk_data.child_ids is not None else [],
                    related_concepts=chunk_data.related_concepts if chunk_data.related_concepts is not None else [],
                    keywords_entities=chunk_data.keywords_entities if chunk_data.keywords_entities is not None else [],
                    formulas=chunk_data.formulas if chunk_data.formulas is not None else [],
                    examples=chunk_data.examples if chunk_data.examples is not None else [],
                    source_uri=chunk_data.source_uri,
                    bbox_coordinates=chunk_data.bbox_coordinates,
                    confidence=chunk_data.confidence if chunk_data.confidence is not None else 1.0,
                    provenance=chunk_data.provenance if chunk_data.provenance is not None else {},
                    relationship_metadata=chunk_data.relationship_metadata if chunk_data.relationship_metadata is not None else {},
                    search_text=chunk_data.search_text,
                    embedding=emb,
                )
                session.add(chunk_record)
                session.flush()

            # 4. Persist Tables & Formulas Assets
            for i, t in enumerate(canonical_doc.tables):
                asset_record = DocumentAsset(
                    document_id=doc_id,
                    page_number=t.page_number,
                    asset_type="table",
                    markdown=t.markdown,
                    html=t.html,
                    bounding_box=t.bbox,
                    caption=t.caption,
                    confidence=t.confidence,
                )
                session.add(asset_record)
                if (i + 1) % 20 == 0:
                    session.flush()

            for i, f in enumerate(canonical_doc.formulas):
                asset_record = DocumentAsset(
                    document_id=doc_id,
                    page_number=f.page_number,
                    asset_type="formula",
                    latex=f.latex,
                    bounding_box=f.bbox,
                    confidence=f.confidence,
                )
                session.add(asset_record)
                if (i + 1) % 20 == 0:
                    session.flush()

            session.flush()

            # 5. Persist Semantic Knowledge Relationships (Graph)
            for i, r in enumerate(canonical_doc.relationships):
                rel_record = KnowledgeRelationship(
                    document_id=doc_id,
                    source_chunk_id=r.source_chunk_id,
                    target_chunk_id=r.target_chunk_id,
                    relation_type=r.relation_type,
                    weight=r.weight,
                    edge_metadata=r.edge_metadata if r.edge_metadata is not None else {},
                )
                session.add(rel_record)
                if (i + 1) % 25 == 0:
                    session.flush()

            session.flush()

            # 6. Persist Processing Stage Metrics & Logs
            if stage_durations:
                for stage_name, duration_ms in stage_durations.items():
                    log_record = ProcessingLog(
                        document_id=doc_id,
                        stage=stage_name,
                        status="SUCCESS",
                        execution_time_ms=duration_ms,
                        metrics={"duration_ms": duration_ms},
                    )
                    session.add(log_record)
                session.flush()

            session.commit()
            logger.info(f"[DataStoragePipeline] Successfully persisted document {doc_id} to database.")
            return True

        except Exception as e:
            session.rollback()
            logger.error(f"[DataStoragePipeline] Database persistence failed for document {doc_id}: {e}")
            raise
