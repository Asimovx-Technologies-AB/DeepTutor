import pytest
from datetime import datetime, timezone
from app.services.storage_pipeline import DataStoragePipeline
from app.schemas.document import (
    CanonicalDocumentRepresentation,
    DocumentMetadataRead,
    PageLayoutInfo,
    StructuralNode,
    RelationshipEdge
)
from app.schemas.chunk import KnowledgeChunkRead
from app.schemas.layout import TableAsset, FormulaAsset
from app.models.document import Document, DocumentPage
from app.models.chunk import KnowledgeChunk
from app.models.relationship import KnowledgeRelationship
from app.models.assets import DocumentAsset


def test_storage_pipeline_persistence(db_session):
    doc_id = "test-doc-persist-1"

    meta = DocumentMetadataRead(
        id=doc_id,
        file_hash="hash_1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef",
        filename="calculus.pdf",
        file_size_bytes=1048576,
        mime_type="application/pdf",
        page_count=2,
        title="Introduction to Calculus",
        author="Leibniz",
        creation_date=datetime.now(timezone.utc),
        pdf_version="1.7",
        status="INDEXED",
        current_stage="COMPLETED",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc)
    )

    page1 = PageLayoutInfo(
        page_number=1, width=612.0, height=792.0, dpi=150, classification="digital", character_density=12.5, blocks=[]
    )

    chunk1 = KnowledgeChunkRead(
        id="chunk-c1",
        document_id=doc_id,
        page_number=1,
        chunk_index=0,
        content="The fundamental theorem of calculus connects differentiation with integration.",
        chunk_type="definition",
        topic="Calculus",
        chapter_section="Chapter 1 > Section 1.1",
        confidence=0.98,
        related_concepts=["differentiation", "integration"],
        keywords_entities=["Fundamental Theorem"],
        formulas=[r"\int_a^b f(x)dx = F(b) - F(a)"],
        examples=[],
        provenance={"parser": "PyMuPDF"},
        relationship_metadata={},
        search_text="calculus fundamental theorem integration differentiation",
    )

    chunk2 = KnowledgeChunkRead(
        id="chunk-c2",
        document_id=doc_id,
        page_number=1,
        chunk_index=1,
        content="Integration can be viewed as the continuous accumulation of infinitesimal quantities.",
        chunk_type="text",
        topic="Calculus",
        chapter_section="Chapter 1 > Section 1.1",
        prev_chunk_id="chunk-c1",
        confidence=0.95,
        related_concepts=["integration", "accumulation"],
        keywords_entities=["Integration"],
        formulas=[],
        examples=[],
        provenance={"parser": "PyMuPDF"},
        relationship_metadata={},
        search_text="integration accumulation infinitesimal quantities",
    )

    table = TableAsset(
        table_index=0, page_number=1, bbox=[50, 100, 300, 200],
        markdown="| Function | Derivative |\n|---|---|\n| x^2 | 2x |",
        confidence=0.95
    )

    formula = FormulaAsset(
        formula_index=0, page_number=1, bbox=[50, 250, 350, 300],
        latex=r"\int_a^b f(x)dx = F(b) - F(a)", confidence=0.99
    )

    relationship = RelationshipEdge(
        source_chunk_id="chunk-c1",
        target_chunk_id="chunk-c2",
        relation_type="elaborates",
        weight=0.9,
        edge_metadata={"shared_concept": "integration"}
    )

    canonical = CanonicalDocumentRepresentation(
        metadata=meta,
        pages=[page1],
        structure_tree=[],
        knowledge_chunks=[chunk1, chunk2],
        tables=[table],
        formulas=[formula],
        relationships=[relationship]
    )

    # Persist via DataStoragePipeline
    success = DataStoragePipeline.persist_canonical_document(
        session=db_session,
        canonical_doc=canonical,
        stage_durations={"PYMUPDF": 15.2, "CHUNKER": 10.1}
    )
    assert success is True

    # Verify rows in DB
    db_doc = db_session.query(Document).filter(Document.id == doc_id).first()
    assert db_doc is not None
    assert db_doc.title == "Introduction to Calculus"

    db_pages = db_session.query(DocumentPage).filter(DocumentPage.document_id == doc_id).all()
    assert len(db_pages) == 1

    db_chunks = db_session.query(KnowledgeChunk).filter(KnowledgeChunk.document_id == doc_id).all()
    assert len(db_chunks) == 2
    assert db_chunks[0].chunk_type == "definition"
    assert db_chunks[1].prev_chunk_id == "chunk-c1"

    db_rels = db_session.query(KnowledgeRelationship).filter(KnowledgeRelationship.document_id == doc_id).all()
    assert len(db_rels) == 1
    assert db_rels[0].relation_type == "elaborates"

    db_assets = db_session.query(DocumentAsset).filter(DocumentAsset.document_id == doc_id).all()
    assert len(db_assets) == 2


def test_bulk_delete_documents(db_session):
    from app.api.documents import bulk_delete_documents, BulkDeleteRequest

    doc1 = Document(
        id="bulk-doc-1",
        file_hash="bulk_hash_1_1234567890abcdef1234567890abcdef1234567890abcdef",
        filename="biology.pdf",
        file_path="storage://biology.pdf",
        file_size_bytes=2048,
        page_count=2,
        title="Biology 101",
        status="INDEXED"
    )
    doc2 = Document(
        id="bulk-doc-2",
        file_hash="bulk_hash_2_1234567890abcdef1234567890abcdef1234567890abcdef",
        filename="chemistry.pdf",
        file_path="storage://chemistry.pdf",
        file_size_bytes=4096,
        page_count=3,
        title="Chemistry 101",
        status="INDEXED"
    )
    doc3 = Document(
        id="bulk-doc-3",
        file_hash="bulk_hash_3_1234567890abcdef1234567890abcdef1234567890abcdef",
        filename="physics.pdf",
        file_path="storage://physics.pdf",
        file_size_bytes=1024,
        page_count=1,
        title="Physics 101",
        status="INDEXED"
    )
    db_session.add_all([doc1, doc2, doc3])

    chunk1 = KnowledgeChunk(
        id="bulk-chunk-1",
        document_id=doc1.id,
        page_number=1,
        chunk_index=0,
        content="Cells are the basic structural units of all organisms.",
        chunk_type="definition",
        topic="Cell Biology",
        search_text="cells basic units organisms"
    )
    db_session.add(chunk1)
    db_session.commit()

    # Bulk delete doc1 and doc2
    req = BulkDeleteRequest(document_ids=[doc1.id, doc2.id])
    res = bulk_delete_documents(payload=req, db=db_session)

    assert res["status"] == "deleted"
    assert res["deleted_count"] == 2
    assert set(res["deleted_ids"]) == {doc1.id, doc2.id}

    # Verify doc1 and doc2 are deleted, along with chunk1
    remaining_docs = db_session.query(Document).filter(Document.id.in_([doc1.id, doc2.id, doc3.id])).all()
    assert len(remaining_docs) == 1
    assert remaining_docs[0].id == doc3.id

    remaining_chunks = db_session.query(KnowledgeChunk).filter(KnowledgeChunk.document_id == doc1.id).all()
    assert len(remaining_chunks) == 0

    # Test empty payload returns 0
    empty_res = bulk_delete_documents(payload=BulkDeleteRequest(document_ids=[]), db=db_session)
    assert empty_res["deleted_count"] == 0

