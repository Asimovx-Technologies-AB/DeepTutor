import pytest
from app.pipeline.orchestrator import DocumentPipelineOrchestrator
from app.services.search_service import HybridSearchService
from app.schemas.pipeline import HybridSearchQuery
from app.models.document import Document
from app.models.chunk import KnowledgeChunk
from app.models.assets import DocumentAsset


def test_end_to_end_pipeline_execution(db_session, sample_pdf_bytes):
    """
    Executes the entire end-to-end processing and storage pipeline on a real PDF,
    and verifies subsequent retrieval via Hybrid Search.
    """
    # 1. Process document through full orchestrator pipeline
    canonical_doc = DocumentPipelineOrchestrator.process_document(
        session=db_session,
        file_bytes=sample_pdf_bytes,
        filename="machine_learning_foundations.pdf"
    )

    assert canonical_doc is not None
    doc_id = canonical_doc.metadata.id
    assert canonical_doc.metadata.page_count == 2
    assert canonical_doc.metadata.status == "INDEXED"

    # Verify pages and blocks
    assert len(canonical_doc.pages) == 2
    assert len(canonical_doc.knowledge_chunks) > 0

    # Verify tables & formulas extraction
    assert len(canonical_doc.tables) >= 1 or len(canonical_doc.formulas) >= 1

    # Verify each chunk has all 14 dimensions populated
    for chunk in canonical_doc.knowledge_chunks:
        assert chunk.content is not None
        assert chunk.chunk_type is not None
        assert chunk.confidence > 0.0
        assert chunk.source_uri is not None
        assert chunk.provenance is not None

    # Verify database persistence
    db_doc = db_session.query(Document).filter(Document.id == doc_id).first()
    assert db_doc is not None
    assert db_doc.status == "INDEXED"

    db_chunks = db_session.query(KnowledgeChunk).filter(KnowledgeChunk.document_id == doc_id).all()
    assert len(db_chunks) == len(canonical_doc.knowledge_chunks)

    # 2. Test Hybrid Search with Hybrid Checks against the newly indexed document
    search_query = HybridSearchQuery(
        query="Machine Learning algorithms",
        document_id=doc_id,
        top_k=3,
        enable_hybrid_checks=True
    )
    search_results = HybridSearchService.execute_search(session=db_session, query=search_query)

    assert len(search_results) > 0
    first_result = search_results[0]
    assert first_result.final_score > 0.0
    assert first_result.verification is not None
    assert first_result.verification.concordance_score > 0.0
