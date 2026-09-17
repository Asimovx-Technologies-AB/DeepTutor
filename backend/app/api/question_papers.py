from typing import List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.models.question_paper import QuestionPaperQuestion, QuestionSupportAnalysis
from app.models.document import Document
from app.pipeline.question_paper_validator import QuestionPaperValidator
from app.tutoring.teaching.study_notes import StudyNotesGenerator

router = APIRouter(prefix="/question-papers", tags=["Question Papers"])

@router.get("/{document_id}/questions")
def get_extracted_questions(document_id: str, db: Session = Depends(get_db)):
    """Retrieve all extracted questions from a Question Paper."""
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found.")
        
    if doc.document_type != "QUESTION_PAPER":
        raise HTTPException(status_code=400, detail="Document is not a Question Paper.")
        
    questions = db.query(QuestionPaperQuestion).filter(QuestionPaperQuestion.document_id == document_id).order_by(QuestionPaperQuestion.extracted_index).all()
    
    return {
        "document_id": document_id,
        "questions": [
            {
                "id": q.id,
                "question_text": q.question_text,
                "marks": q.marks,
                "question_type": q.question_type,
                "cognitive_level": q.cognitive_level
            } for q in questions
        ]
    }

@router.post("/{document_id}/validate/{study_material_id}")
def validate_question_paper(document_id: str, study_material_id: str, db: Session = Depends(get_db)):
    """Validates the questions in a Question Paper against a Study Material."""
    q_doc = db.query(Document).filter(Document.id == document_id).first()
    s_doc = db.query(Document).filter(Document.id == study_material_id).first()
    
    if not q_doc or not s_doc:
        raise HTTPException(status_code=404, detail="One or both documents not found.")
        
    results = QuestionPaperValidator.validate_paper(db, document_id, study_material_id)
    
    return {
        "status": "success",
        "validated_questions_count": len(results),
        "results": [
            {
                "question_id": r.question_id,
                "status": r.status,
                "confidence": r.confidence,
                "evidence_summary": r.evidence_summary
            } for r in results
        ]
    }
    
@router.post("/{document_id}/generate-notes/{study_material_id}")
def generate_study_notes(document_id: str, study_material_id: str, db: Session = Depends(get_db)):
    """Generates study notes for the Question Paper based on the Study Material."""
    q_doc = db.query(Document).filter(Document.id == document_id).first()
    s_doc = db.query(Document).filter(Document.id == study_material_id).first()
    
    if not q_doc or not s_doc:
        raise HTTPException(status_code=404, detail="One or both documents not found.")
        
    notes = StudyNotesGenerator.generate_question_paper_notes(db, document_id, study_material_id)
    
    return {
        "status": "success",
        "study_notes": notes
    }
