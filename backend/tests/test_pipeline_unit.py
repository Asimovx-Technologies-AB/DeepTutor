import pytest
from app.pipeline.metadata_extractor import MetadataExtractor
from app.pipeline.pdf_parser import PyMuPDFParser
from app.pipeline.classifier import DocumentClassifier
from app.pipeline.text_pipeline.quality_checker import TextQualityChecker
from app.pipeline.text_pipeline.normalizer import TextNormalizer
from app.pipeline.visual_pipeline.layout_analyzer import LayoutAnalyzer
from app.pipeline.visual_pipeline.table_detector import TableDetector
from app.pipeline.visual_pipeline.formula_detector import FormulaDetector
from app.pipeline.structure_builder import DocumentStructureBuilder
from app.pipeline.semantic_extractor import SemanticKnowledgeExtractor
from app.schemas.layout import LayoutBlock


def test_metadata_extraction(sample_pdf_bytes):
    meta = MetadataExtractor.extract_pdf_metadata(sample_pdf_bytes, "test_doc.pdf")
    assert meta["file_hash"] is not None
    assert len(meta["file_hash"]) == 64
    assert meta["page_count"] == 2
    assert meta["file_size_bytes"] > 0
    assert meta["mime_type"] == "application/pdf"


def test_pymupdf_parser(sample_pdf_bytes):
    parser = PyMuPDFParser(render_dpi=72)
    pages = parser.parse_document(sample_pdf_bytes, "doc-test-123")
    assert len(pages) == 2
    assert pages[0]["page_number"] == 1
    assert pages[0]["width"] == 612.0
    assert pages[0]["height"] == 792.0
    assert len(pages[0]["blocks"]) > 0
    assert "Machine Learning" in pages[0]["raw_text"]


def test_document_classification():
    page_data = {"char_count": 500, "blocks": [{"type": "text"}, {"type": "text"}]}
    assert DocumentClassifier.classify_page(page_data) == "digital"

    scanned_data = {"char_count": 10, "blocks": []}
    assert DocumentClassifier.classify_page(scanned_data) == "scanned"


def test_text_quality_checker():
    clean_text = "This is a clean English sentence with proper vocabulary and grammatical syntax."
    score, decision = TextQualityChecker.evaluate_quality(clean_text)
    assert decision == "GOOD"
    assert score >= 0.7

    corrupted_text = "^^~~~__||\\//???? ???"
    c_score, c_decision = TextQualityChecker.evaluate_quality(corrupted_text)
    assert c_decision == "POOR"
    assert c_score < 0.5


def test_text_normalizer():
    raw = "The deep-learning transfor-\nmation ﬁnally began."
    normalized = TextNormalizer.normalize(raw)
    assert "transformation" in normalized
    assert "finally" in normalized # Ligature resolved


def test_table_detector():
    table_block = LayoutBlock(
        block_index=0,
        reading_order=0,
        bbox=[50, 50, 400, 200],
        text="Name | Age | Role\nAlice | 28 | Engineer\nBob | 34 | Architect"
    )
    tables, regular = TableDetector.detect_tables([table_block], page_number=1)
    assert len(tables) == 1
    assert tables[0].headers == ["Name", "Age", "Role"]
    assert len(tables[0].rows) == 2
    assert "| Alice | 28 | Engineer |" in tables[0].markdown


def test_formula_detector():
    formula_block = LayoutBlock(
        block_index=1,
        reading_order=1,
        bbox=[50, 200, 350, 250],
        text="E = m c^2"
    )
    formulas, modified = FormulaDetector.detect_formulas([formula_block], page_number=1)
    assert len(formulas) == 1
    assert "c^2" in formulas[0].latex


def test_structure_builder():
    blocks_p1 = [
        LayoutBlock(block_index=0, reading_order=0, bbox=[50, 50, 400, 80], text="Chapter 1: Foundations", block_type="heading"),
        LayoutBlock(block_index=1, reading_order=1, bbox=[50, 90, 400, 110], text="1.1 Overview", block_type="heading"),
    ]
    pages_blocks = [{"page_number": 1, "blocks": blocks_p1}]
    tree = DocumentStructureBuilder.build_structure(pages_blocks)
    assert len(tree) >= 1
    assert "Foundations" in tree[0].title
    assert len(tree[0].children) >= 1
    assert "1.1 Overview" in tree[0].children[0].title


def test_semantic_extractor():
    sample_text = (
        "Neural Network is defined as a series of algorithms that mimic human cognitive operations. "
        "For example, convolutional networks process 2D image matrices."
    )
    semantics = SemanticKnowledgeExtractor.extract_semantics(sample_text, "Chapter 1")
    assert semantics["inferred_type"] == "definition"
    assert len(semantics["definitions"]) >= 1
    assert len(semantics["examples"]) >= 1
    assert len(semantics["keywords_entities"]) >= 1
