import logging
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, BackgroundTasks
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.models.document import Document, DocumentPage
from app.models.chunk import KnowledgeChunk
from app.models.assets import DocumentAsset
from app.models.relationship import KnowledgeRelationship
from app.schemas.document import (
    DocumentMetadataRead,
    CanonicalDocumentRepresentation,
    PageLayoutInfo,
    StructuralNode,
    RelationshipEdge
)
from app.schemas.chunk import KnowledgeChunkRead
from app.schemas.layout import TableAsset, FormulaAsset
from app.pipeline.orchestrator import DocumentPipelineOrchestrator

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/documents", tags=["Documents"])


from fastapi import Form
from app.models.session import StudySession, CurriculumTopic


@router.post("/upload")
async def upload_and_process_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    topic_id: Optional[str] = Form(None),
    section_id: Optional[str] = Form(None),
    db: Session = Depends(get_db)
):
    """
    Uploads a PDF document, performs fast in-memory extraction for immediate (< 1s) access,
    initializes the StudySession and curriculum topics, and schedules deep pipeline
    processing (tables, formulas, 14-dimension chunks) in the background.
    """
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are currently supported.")

    file_bytes = await file.read()
    if not file_bytes:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    import hashlib
    import uuid
    import fitz
    from app.storage.local_storage import default_storage

    file_hash = hashlib.sha256(file_bytes).hexdigest()
    existing_doc = db.query(Document).filter(Document.file_hash == file_hash).first()
    if existing_doc:
        chunk_count = db.query(KnowledgeChunk).filter(KnowledgeChunk.document_id == existing_doc.id).count()
        if chunk_count > 0:
            doc_id = existing_doc.id
            doc_title = existing_doc.title or file.filename

            study_sess = StudySession(
                document_id=doc_id,
                subject="Uploaded PDF Study",
                title=doc_title,
                document_name=file.filename,
                status="active"
            )
            db.add(study_sess)
            db.flush()

            existing_topics = (
                db.query(CurriculumTopic)
                .filter(CurriculumTopic.document_id == doc_id)
                .order_by(CurriculumTopic.order_index)
                .all()
            )
            seen_titles = set()
            order_idx = 0
            for t in existing_topics:
                if t.title not in seen_titles:
                    seen_titles.add(t.title)
                    db.add(CurriculumTopic(
                        session_id=study_sess.id,
                        document_id=doc_id,
                        title=t.title,
                        summary=t.summary,
                        order_index=order_idx,
                        structural_path=t.structural_path,
                        page_start=t.page_start,
                        page_end=t.page_end
                    ))
                    order_idx += 1

            if order_idx == 0:
                db.add(CurriculumTopic(
                    session_id=study_sess.id,
                    document_id=doc_id,
                    title="Chapter Overview",
                    summary="Full document curriculum",
                    order_index=0,
                    page_start=1,
                    page_end=existing_doc.page_count
                ))

            db.commit()
            return {
                "status": "success",
                "document_id": doc_id,
                "session_id": study_sess.id,
                "filename": file.filename,
                "title": doc_title,
                "page_count": existing_doc.page_count,
                "chunks_count": chunk_count,
                "canonical": None
            }

    try:
        # Fast synchronous ingestion phase (< 500ms):
        # 1. Save raw PDF to storage
        raw_storage_path = default_storage.store_file(file_bytes, file.filename, subfolder="raw_documents")

        # 2. In-memory fast PDF metadata and TOC extraction
        from app.pipeline.metadata_extractor import MetadataExtractor
        meta_dict = MetadataExtractor.extract_pdf_metadata(file_bytes, file.filename)
        doc_id = existing_doc.id if existing_doc else str(uuid.uuid4())
        pdf_doc = fitz.open(stream=file_bytes, filetype="pdf")
        page_count = meta_dict["page_count"] or len(pdf_doc)
        doc_title = meta_dict["title"] or file.filename

        # 3. Create or update Document record
        if not existing_doc:
            db_doc = Document(
                id=doc_id,
                file_hash=file_hash,
                filename=file.filename,
                file_path=raw_storage_path,
                file_size_bytes=len(file_bytes),
                mime_type="application/pdf",
                page_count=page_count,
                title=doc_title,
                author=meta_dict.get("author") or "Unknown",
                creation_date=meta_dict.get("creation_date"),
                pdf_version=meta_dict.get("pdf_version") or "1.4",
                status="PROCESSING",
                current_stage="PARSING",
            )
            db.add(db_doc)
        else:
            existing_doc.status = "PROCESSING"
            existing_doc.current_stage = "PARSING"
            existing_doc.page_count = page_count
            existing_doc.title = doc_title
        db.flush()

        # 4. Create StudySession
        study_sess = StudySession(
            document_id=doc_id,
            subject="Uploaded PDF Study",
            title=doc_title,
            document_name=file.filename,
            status="active"
        )
        db.add(study_sess)
        db.flush()

        # 5. Extract Table of Contents / Topics
        toc = pdf_doc.get_toc()
        topics_list = []
        if toc:
            for item in toc:
                lvl, t_title, p_num = item[0], item[1].strip(), item[2]
                if t_title and (lvl == 1 or (lvl <= 2 and len(topics_list) < 20)):
                    topics_list.append((t_title, p_num))

        if not topics_list:
            step = max(5, page_count // 5) if page_count > 10 else page_count
            for start_p in range(1, page_count + 1, step):
                end_p = min(start_p + step - 1, page_count)
                topics_list.append((f"Section {len(topics_list)+1}: Pages {start_p}-{end_p}", start_p))

        for idx, (t_title, p_start) in enumerate(topics_list):
            next_p = topics_list[idx + 1][1] if idx + 1 < len(topics_list) else page_count
            p_end = max(p_start, next_p if idx + 1 < len(topics_list) else page_count)
            db.add(CurriculumTopic(
                session_id=study_sess.id,
                document_id=doc_id,
                title=t_title,
                summary=f"Pages {p_start} - {p_end}",
                order_index=idx,
                structural_path=t_title,
                page_start=p_start,
                page_end=p_end
            ))

        # 6. Extract immediate initial knowledge chunks from pages (for immediate querying)
        initial_chunks = []
        max_preview_pages = min(page_count, 100)
        for p_idx in range(max_preview_pages):
            page = pdf_doc[p_idx]
            p_text = page.get_text().strip()
            if p_text and len(p_text) > 30:
                assigned_topic = topics_list[0][0] if topics_list else "General"
                for t_title, p_start in topics_list:
                    if p_idx + 1 >= p_start:
                        assigned_topic = t_title

                chunk_id = str(uuid.uuid4())
                initial_chunks.append(KnowledgeChunk(
                    id=chunk_id,
                    document_id=doc_id,
                    page_number=p_idx + 1,
                    chunk_index=len(initial_chunks),
                    content=p_text[:2500],
                    chunk_type="text",
                    topic=assigned_topic,
                    chapter_section=assigned_topic,
                    confidence=1.0,
                    search_text=p_text[:1200]
                ))

        if initial_chunks:
            db.bulk_save_objects(initial_chunks)

        db.commit()

        # 7. Add deep processing to BackgroundTasks
        background_tasks.add_task(
            DocumentPipelineOrchestrator.process_document_background,
            doc_id,
            file_bytes,
            file.filename
        )

        # 8. Return immediately in < 1 second!
        return {
            "status": "success",
            "document_id": doc_id,
            "session_id": study_sess.id,
            "filename": file.filename,
            "title": doc_title,
            "page_count": page_count,
            "chunks_count": len(initial_chunks),
            "canonical": None
        }
    except Exception as e:
        logger.error(f"Error processing uploaded document: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Pipeline processing failed: {str(e)}")


@router.get("/{doc_id}/status")
def get_document_status(doc_id: str, db: Session = Depends(get_db)):
    """Status endpoint polled by documentsApi.status."""
    doc = db.query(Document).filter(Document.id == doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found.")
    return {
        "id": doc.id,
        "status": doc.status,
        "current_stage": doc.current_stage,
        "page_count": doc.page_count,
        "error_message": doc.error_message
    }


@router.get("", response_model=List[DocumentMetadataRead])
def list_documents(
    skip: int = 0,
    limit: int = 50,
    db: Session = Depends(get_db)
):
    """Lists all stored documents, deduplicated by file_hash, enriched with topics and sessions."""
    # Deduplicate documents by file_hash (keep most recent)
    all_docs = db.query(Document).order_by(Document.created_at.desc()).all()
    seen_hashes = set()
    unique_docs = []
    for d in all_docs:
        if d.file_hash not in seen_hashes:
            seen_hashes.add(d.file_hash)
            unique_docs.append(d)

    paged_docs = unique_docs[skip : skip + limit]
    results = []

    for doc in paged_docs:
        # 1. Fetch linked sessions
        sessions = db.query(StudySession).filter(StudySession.document_id == doc.id).all()
        session_list = [
            {
                "id": s.id,
                "title": s.title,
                "subject": s.subject,
                "created_at": s.created_at.isoformat() if s.created_at else None,
            }
            for s in sessions
        ]

        # 2. Determine subject
        detected_subject = (
            sessions[0].subject if sessions and sessions[0].subject and sessions[0].subject != "General Study"
            else doc.title or "General Study"
        )

        # 3. Extract key topics
        curriculum_topics = (
            db.query(CurriculumTopic)
            .filter(CurriculumTopic.document_id == doc.id)
            .order_by(CurriculumTopic.order_index)
            .limit(10)
            .all()
        )
        key_topics = []
        if curriculum_topics:
            for ct in curriculum_topics:
                t_title = ct.title.strip()
                if t_title and len(t_title) < 50 and t_title not in key_topics:
                    key_topics.append(t_title)
        else:
            # Fallback to chunk topics
            chunks = (
                db.query(KnowledgeChunk)
                .filter(KnowledgeChunk.document_id == doc.id, KnowledgeChunk.topic.isnot(None))
                .limit(10)
                .all()
            )
            for ch in chunks:
                if ch.topic and ch.topic not in key_topics and len(ch.topic) < 50:
                    key_topics.append(ch.topic)

        doc_dict = {
            "id": doc.id,
            "file_hash": doc.file_hash,
            "filename": doc.filename,
            "file_size_bytes": doc.file_size_bytes,
            "mime_type": doc.mime_type,
            "page_count": doc.page_count,
            "title": doc.title,
            "author": doc.author,
            "creation_date": doc.creation_date,
            "pdf_version": doc.pdf_version,
            "status": doc.status,
            "current_stage": doc.current_stage,
            "error_message": doc.error_message,
            "created_at": doc.created_at,
            "updated_at": doc.updated_at,
            "key_topics": key_topics[:6],
            "detected_subject": detected_subject,
            "session_count": len(session_list),
            "linked_sessions": session_list,
            "file_name": doc.filename,
            "file_type": "PDF" if (doc.mime_type and "pdf" in doc.mime_type.lower()) or (doc.filename and doc.filename.lower().endswith(".pdf")) else "DOC",
            "doc_hash": doc.file_hash,
            "indexed": doc.status == "INDEXED",
            "index_status": "done" if doc.status == "INDEXED" else "processing",
        }
        results.append(DocumentMetadataRead(**doc_dict))

    return results


@router.post("/link-to-session")
def link_document_to_session(
    payload: dict,
    db: Session = Depends(get_db)
):
    """
    Links a previously uploaded document to a StudySession.
    Copies curriculum topics and updates session document reference.
    """
    session_id = payload.get("session_id")
    doc_id = payload.get("doc_id")
    doc_hash = payload.get("doc_hash")
    filename = payload.get("filename")

    if not session_id:
        raise HTTPException(status_code=400, detail="session_id is required.")

    sess = db.query(StudySession).filter(StudySession.id == session_id).first()
    if not sess:
        # Create session if needed
        sess = StudySession(
            id=session_id,
            title=f"{filename or 'Material'} Study Room",
            subject="General Study",
            status="active"
        )
        db.add(sess)
        db.flush()

    # Find the document
    doc = None
    if doc_id:
        doc = db.query(Document).filter(Document.id == doc_id).first()
    if not doc and doc_hash:
        doc = db.query(Document).filter(Document.file_hash == doc_hash).first()
    if not doc and filename:
        doc = db.query(Document).filter(Document.filename == filename).first()

    if not doc:
        raise HTTPException(status_code=404, detail="Document not found.")

    sess.document_id = doc.id
    sess.document_name = doc.filename
    if doc.title and (sess.title == "Study Session" or not sess.title):
        sess.title = f"{doc.title} Study Room"

    # Attach curriculum topics to this session if not present
    existing_topics = db.query(CurriculumTopic).filter(CurriculumTopic.session_id == session_id).all()
    if not existing_topics:
        # Check if topics exist under document
        doc_topics = db.query(CurriculumTopic).filter(CurriculumTopic.document_id == doc.id).all()
        if doc_topics:
            for dt in doc_topics:
                new_topic = CurriculumTopic(
                    session_id=session_id,
                    document_id=doc.id,
                    title=dt.title,
                    summary=dt.summary,
                    order_index=dt.order_index,
                    structural_path=dt.structural_path,
                    page_start=dt.page_start,
                    page_end=dt.page_end,
                )
                db.add(new_topic)
        else:
            # Fallback default topic from chunks
            chunks = db.query(KnowledgeChunk).filter(KnowledgeChunk.document_id == doc.id).order_by(KnowledgeChunk.chunk_index).all()
            if chunks:
                seen_chunk_topics = set()
                order_idx = 0
                for c in chunks:
                    t_name = c.chapter_section or c.topic or "Overview"
                    if t_name not in seen_chunk_topics:
                        seen_chunk_topics.add(t_name)
                        db.add(CurriculumTopic(
                            session_id=session_id,
                            document_id=doc.id,
                            title=t_name,
                            summary=f"Section from {doc.filename}",
                            order_index=order_idx,
                            page_start=c.page_number,
                            page_end=c.page_number,
                        ))
                        order_idx += 1
                        if order_idx >= 15:
                            break

    db.commit()
    db.refresh(sess)

    all_sess_topics = db.query(CurriculumTopic).filter(CurriculumTopic.session_id == session_id).order_by(CurriculumTopic.order_index).all()

    return {
        "status": "success",
        "session_id": sess.id,
        "document_id": doc.id,
        "filename": doc.filename,
        "documents": [doc.filename],
        "topics": [
            {
                "id": t.id,
                "title": t.title,
                "summary": t.summary,
                "order_index": t.order_index,
                "page_start": t.page_start,
                "page_end": t.page_end,
            }
            for t in all_sess_topics
        ]
    }


@router.get("/{doc_id}", response_model=DocumentMetadataRead)
def get_document_metadata(
    doc_id: str,
    db: Session = Depends(get_db)
):
    """Retrieves document metadata by ID."""
    doc = db.query(Document).filter(Document.id == doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found.")
    return doc


@router.get("/{doc_id}/canonical", response_model=CanonicalDocumentRepresentation)
def get_canonical_document(
    doc_id: str,
    db: Session = Depends(get_db)
):
    """Retrieves the full Canonical Document Representation."""
    doc = db.query(Document).filter(Document.id == doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found.")

    # 1. Fetch Pages
    pages = db.query(DocumentPage).filter(DocumentPage.document_id == doc_id).order_by(DocumentPage.page_number).all()
    page_infos = [
        PageLayoutInfo(
            page_number=p.page_number,
            width=p.width,
            height=p.height,
            dpi=p.dpi,
            classification=p.classification,
            character_density=p.character_density,
            blocks=[]
        ) for p in pages
    ]

    # 2. Fetch Chunks
    chunks = db.query(KnowledgeChunk).filter(KnowledgeChunk.document_id == doc_id).order_by(KnowledgeChunk.chunk_index).all()
    chunk_reads = [KnowledgeChunkRead.model_validate(c) for c in chunks]

    # 3. Fetch Tables & Formulas
    assets = db.query(DocumentAsset).filter(DocumentAsset.document_id == doc_id).all()
    tables = [
        TableAsset(
            table_index=idx,
            page_number=a.page_number,
            bbox=a.bounding_box or [0, 0, 0, 0],
            markdown=a.markdown or "",
            html=a.html,
            caption=a.caption,
            confidence=a.confidence
        ) for idx, a in enumerate(assets) if a.asset_type == "table"
    ]
    formulas = [
        FormulaAsset(
            formula_index=idx,
            page_number=a.page_number,
            bbox=a.bounding_box or [0, 0, 0, 0],
            latex=a.latex or "",
            confidence=a.confidence
        ) for idx, a in enumerate(assets) if a.asset_type == "formula"
    ]

    # 4. Fetch Relationships
    relationships = db.query(KnowledgeRelationship).filter(KnowledgeRelationship.document_id == doc_id).all()
    rel_edges = [
        RelationshipEdge(
            source_chunk_id=r.source_chunk_id,
            target_chunk_id=r.target_chunk_id,
            relation_type=r.relation_type,
            weight=r.weight,
            edge_metadata=r.edge_metadata or {}
        ) for r in relationships
    ]

    # 5. Build basic structure tree
    structure_tree = [
        StructuralNode(
            id=doc.id,
            title=doc.title or doc.filename,
            level=1,
            path=doc.title or doc.filename,
            page_start=1,
            page_end=doc.page_count,
            chunk_ids=[c.id for c in chunks]
        )
    ]

    return CanonicalDocumentRepresentation(
        metadata=DocumentMetadataRead.model_validate(doc),
        pages=page_infos,
        structure_tree=structure_tree,
        knowledge_chunks=chunk_reads,
        tables=tables,
        formulas=formulas,
        relationships=rel_edges,
    )


@router.delete("/{doc_id}")
def delete_document(
    doc_id: str,
    db: Session = Depends(get_db)
):
    """Deletes a document and all related pages, chunks, and assets."""
    doc = db.query(Document).filter(Document.id == doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found.")

    db.delete(doc)
    db.commit()
    return {"status": "deleted", "id": doc_id}
