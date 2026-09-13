import pytest
from app.models.chunk import KnowledgeChunk
from app.models.relationship import KnowledgeRelationship
from app.schemas.pipeline import HybridSearchQuery
from app.services.search_service import HybridSearchService


def test_hybrid_search_with_hybrid_checks(db_session):
    doc_id = "test-doc-search-1"

    # Insert sample chunks
    c1 = KnowledgeChunk(
        id="search-chunk-1",
        document_id=doc_id,
        page_number=1,
        chunk_index=0,
        content="Backpropagation algorithm computes gradient vectors for neural network weights.",
        chunk_type="text",
        topic="Neural Networks",
        chapter_section="Chapter 3 > Optimization",
        related_concepts=["backpropagation", "gradient"],
        keywords_entities=["Backpropagation", "Neural Network"],
        confidence=0.99,
        search_text="Backpropagation algorithm computes gradient vectors for neural network weights."
    )
    c2 = KnowledgeChunk(
        id="search-chunk-2",
        document_id=doc_id,
        page_number=1,
        chunk_index=1,
        content="Stochastic Gradient Descent updates parameters using mini-batch gradient estimations.",
        chunk_type="text",
        topic="Optimization",
        chapter_section="Chapter 3 > Optimization",
        related_concepts=["gradient", "descent"],
        keywords_entities=["Stochastic Gradient Descent"],
        confidence=0.95,
        search_text="Stochastic Gradient Descent updates parameters using mini-batch gradient estimations."
    )
    db_session.add_all([c1, c2])
    db_session.flush()

    # Link chunks with a relationship edge
    rel = KnowledgeRelationship(
        id="rel-1",
        document_id=doc_id,
        source_chunk_id="search-chunk-1",
        target_chunk_id="search-chunk-2",
        relation_type="elaborates",
        weight=0.9
    )
    db_session.add(rel)
    db_session.commit()

    # Perform Hybrid Search
    query = HybridSearchQuery(
        query="Backpropagation gradient",
        top_k=2,
        enable_hybrid_checks=True
    )
    results = HybridSearchService.execute_search(session=db_session, query=query)

    assert len(results) > 0
    top_result = results[0]
    assert top_result.chunk.id == "search-chunk-1"
    assert top_result.final_score > 0.0

    # Verify Hybrid Check details
    assert top_result.verification is not None
    assert top_result.verification.fts_matched is True
    assert top_result.verification.concordance_score > 0.0
    assert top_result.verification.verification_status in ["VERIFIED", "PARTIAL", "WEAK"]
    assert len(top_result.verification.verification_notes) > 0
