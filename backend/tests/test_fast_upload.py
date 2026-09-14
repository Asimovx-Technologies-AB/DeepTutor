import pytest
import io
import fitz
from fastapi import BackgroundTasks
from fastapi.datastructures import UploadFile
from app.api.documents import upload_and_process_document
from app.models.document import Document
from app.models.chunk import KnowledgeChunk
from app.models.session import StudySession, CurriculumTopic


@pytest.mark.asyncio
async def test_fast_upload_creates_session_and_chunks_instantly(db_session):
    # 1. Create a minimal 3-page test PDF with text and TOC in-memory
    doc = fitz.open()
    
    # Page 1
    p1 = doc.new_page()
    p1.insert_text((50, 50), "Chapter 1: Foundations of Quantum Physics\nThis chapter introduces quantum states and operators.")
    
    # Page 2
    p2 = doc.new_page()
    p2.insert_text((50, 50), "Chapter 2: Wave Mechanics and Schrödinger Equation\nDescribes wave function propagation over time.")
    
    # Page 3
    p3 = doc.new_page()
    p3.insert_text((50, 50), "Chapter 3: Quantum Superposition and Entanglement\nBell inequalities and entangled photon pairs.")
    
    # Set TOC: [level, title, page_number]
    doc.set_toc([
        [1, "Chapter 1: Foundations", 1],
        [1, "Chapter 2: Wave Mechanics", 2],
        [1, "Chapter 3: Quantum Superposition", 3],
    ])
    
    pdf_bytes = doc.write()
    doc.close()

    upload_file = UploadFile(
        filename="quantum_physics_intro.pdf",
        file=io.BytesIO(pdf_bytes)
    )

    bg_tasks = BackgroundTasks()

    # 2. Call upload_and_process_document
    response = await upload_and_process_document(
        background_tasks=bg_tasks,
        file=upload_file,
        topic_id=None,
        section_id=None,
        db=db_session
    )

    # 3. Assert fast immediate response
    assert response["status"] == "success"
    assert response["page_count"] == 3
    assert response["chunks_count"] >= 3
    assert response["document_id"] is not None
    assert response["session_id"] is not None
    assert len(bg_tasks.tasks) == 1  # Deep processing background task queued

    doc_id = response["document_id"]
    sess_id = response["session_id"]

    # 4. Verify DB persistence of preliminary objects
    db_doc = db_session.query(Document).filter(Document.id == doc_id).first()
    assert db_doc is not None
    assert db_doc.status == "PROCESSING"

    db_sess = db_session.query(StudySession).filter(StudySession.id == sess_id).first()
    assert db_sess is not None
    assert db_sess.document_id == doc_id

    topics = db_session.query(CurriculumTopic).filter(CurriculumTopic.document_id == doc_id).all()
    assert len(topics) == 3
    topic_titles = [t.title for t in topics]
    assert "Chapter 1: Foundations" in topic_titles
    assert "Chapter 2: Wave Mechanics" in topic_titles
    assert "Chapter 3: Quantum Superposition" in topic_titles

    chunks = db_session.query(KnowledgeChunk).filter(KnowledgeChunk.document_id == doc_id).all()
    assert len(chunks) == 3
    assert any("quantum states and operators" in c.content for c in chunks)
