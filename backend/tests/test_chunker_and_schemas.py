import pytest
from app.pipeline.chunker import KnowledgeChunker
from app.pipeline.quality_validator import QualityValidator
from app.pipeline.canonical import CanonicalDocumentBuilder
from app.schemas.layout import LayoutBlock, TableAsset, FormulaAsset
from app.schemas.document import StructuralNode


def test_14_dimensions_in_knowledge_chunks():
    """Verify that KnowledgeChunker strictly outputs all 14 dimensions."""
    blocks = [
        LayoutBlock(
            block_index=0, reading_order=0, bbox=[50, 50, 500, 100],
            text="Quantum Computing is defined as a multidisciplinary field comprising aspects of computer science, physics, and mathematics.",
            block_type="text"
        )
    ]
    pages_data = [{"page_number": 1, "width": 612.0, "height": 792.0, "blocks": blocks}]
    structure_tree = [
        StructuralNode(
            id="node-1", title="Quantum Computing", level=1, path="Quantum Computing",
            page_start=1, page_end=1, chunk_ids=[]
        )
    ]
    tables = []
    formulas = [
        FormulaAsset(formula_index=0, page_number=1, bbox=[50, 120, 200, 150], latex=r"|\psi\rangle = \alpha|0\rangle + \beta|1\rangle")
    ]

    chunks = KnowledgeChunker.generate_chunks(
        doc_id="doc-quantum-1",
        pages_data=pages_data,
        structure_tree=structure_tree,
        tables=tables,
        formulas=formulas
    )

    assert len(chunks) == 1
    c = chunks[0]

    # Check all 14 dimensions:
    assert "content" in c # Dim 1
    assert "chunk_type" in c # Dim 2
    assert "topic" in c # Dim 3
    assert "chapter_section" in c # Dim 4
    assert "prev_chunk_id" in c # Dim 5
    assert "next_chunk_id" in c # Dim 6
    assert "parent_id" in c # Dim 7
    assert "related_concepts" in c # Dim 7 (concepts)
    assert "keywords_entities" in c # Dim 8
    assert "formulas" in c # Dim 9
    assert "examples" in c # Dim 10
    assert "source_uri" in c # Dim 11
    assert "confidence" in c # Dim 12
    assert "provenance" in c # Dim 13
    assert "relationship_metadata" in c # Dim 14

    assert len(c["formulas"]) == 1
    assert c["confidence"] > 0.0
    assert c["parent_id"] == "node-1"


def test_quality_validation():
    valid_chunk = {
        "id": "c-1",
        "content": "This is a sufficiently long valid knowledge chunk containing valuable technical explanations.",
        "chunk_type": "text",
        "confidence": 0.95
    }
    short_bad_chunk = {
        "id": "c-2",
        "content": "a",
        "chunk_type": "text",
        "confidence": 0.2
    }
    relationships = [
        {"source_chunk_id": "c-1", "target_chunk_id": "c-2", "relation_type": "defines"}
    ]

    valid_chunks, valid_rels, metrics = QualityValidator.validate_chunks([valid_chunk, short_bad_chunk], relationships)
    assert len(valid_chunks) == 1
    assert valid_chunks[0]["id"] == "c-1"
    # Bad chunk was dropped, so dangling relationship must also be removed
    assert len(valid_rels) == 0
    assert metrics["dropped_chunks"] == 1
