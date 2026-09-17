import pytest
from app.tutoring.analyzer.output_compliance import OutputComplianceValidator
from app.schemas.tutoring import OutputRequirements
from app.models.question_paper import QuestionPaperQuestion, QuestionSupportAnalysis
from app.pipeline.question_extractor import QuestionPaperExtractor
from app.pipeline.question_paper_validator import QuestionPaperValidator

def test_output_compliance_answer_only():
    reqs = OutputRequirements(format="ANSWER_ONLY")
    bad_text = "Here is the answer for your question: 42.\n### 💡 Interactive Checkpoint\nWhat do you think?"
    validation = OutputComplianceValidator.validate_response(bad_text, reqs)
    assert not validation["is_compliant"]
    assert any("conversational filler" in r for r in validation["reasons"])

    good_text = "42"
    good_validation = OutputComplianceValidator.validate_response(good_text, reqs)
    assert good_validation["is_compliant"]

def test_output_compliance_bullets_only():
    reqs = OutputRequirements(format="BULLETS_ONLY")
    prose_text = "Machine Learning is very interesting.\nIt has multiple paradigms.\nOne paradigm is supervised learning.\nAnother is unsupervised learning."
    validation = OutputComplianceValidator.validate_response(prose_text, reqs)
    assert not validation["is_compliant"]
    assert any("BULLETS_ONLY" in r for r in validation["reasons"])

    bullet_text = "- Machine learning is a branch of AI\n- Supervised learning uses labeled data\n- Unsupervised learning finds patterns"
    good_validation = OutputComplianceValidator.validate_response(bullet_text, reqs)
    assert good_validation["is_compliant"]

def test_output_compliance_short_length():
    reqs = OutputRequirements(length="SHORT")
    long_text = "word " * 120
    validation = OutputComplianceValidator.validate_response(long_text, reqs)
    assert not validation["is_compliant"]
    assert any("too long" in r for r in validation["reasons"])

    short_text = "This is a concise explanation under twenty words."
    good_validation = OutputComplianceValidator.validate_response(short_text, reqs)
    assert good_validation["is_compliant"]

def test_output_compliance_disallow_examples():
    reqs = OutputRequirements(include_examples=False)
    text_with_example = "Gradient descent is an optimizer. For example, descending down a misty mountain."
    validation = OutputComplianceValidator.validate_response(text_with_example, reqs)
    assert not validation["is_compliant"]
    assert any("include_examples=False" in r for r in validation["reasons"])

def test_question_paper_models_instantiation():
    q = QuestionPaperQuestion(
        document_id="doc-123",
        question_number="1a",
        question_text="Explain gradient descent.",
        section="Part A",
        marks=5.0,
        source_page=2,
        topics=["Optimization", "Gradient Descent"]
    )
    assert q.document_id == "doc-123"
    assert q.question_number == "1a"
    assert q.marks == 5.0
    assert "Optimization" in q.topics

    analysis = QuestionSupportAnalysis(
        question_id=q.id,
        study_material_id="mat-456",
        status="SUPPORTED",
        confidence=0.95,
        evidence_summary="Topic is thoroughly covered on page 14.",
        source_pages=[14],
        source_chunk_ids=["chunk-1"]
    )
    assert analysis.status == "SUPPORTED"
    assert analysis.confidence == 0.95
    assert analysis.source_pages == [14]

def test_question_paper_extractor_system_prompt():
    assert "extract individual questions" in QuestionPaperExtractor.SYSTEM_PROMPT.lower()
    assert "question_number" in QuestionPaperExtractor.SYSTEM_PROMPT
    assert "question_text" in QuestionPaperExtractor.SYSTEM_PROMPT

def test_question_paper_validator_system_prompt():
    assert "SUPPORTED" in QuestionPaperValidator.SYSTEM_PROMPT
    assert "PARTIALLY_SUPPORTED" in QuestionPaperValidator.SYSTEM_PROMPT
    assert "NOT_SUPPORTED" in QuestionPaperValidator.SYSTEM_PROMPT
