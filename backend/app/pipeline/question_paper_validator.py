import json
import logging
from typing import List
from sqlalchemy.orm import Session
from app.models.question_paper import QuestionPaperQuestion, QuestionSupportAnalysis
from app.schemas.pipeline import HybridSearchQuery
from app.services.search_service import HybridSearchService
from app.services.llm_service import default_llm_service

logger = logging.getLogger(__name__)

class QuestionPaperValidator:
    """
    Validates if extracted QuestionPaperQuestions are supported by the provided Study Material document.
    """

    SYSTEM_PROMPT = """You are an expert academic evaluator. Your task is to determine if a given test question can be answered using ONLY the provided study material chunks.

You must output a JSON object with the following schema:
{
    "status": "String (SUPPORTED, PARTIALLY_SUPPORTED, NOT_SUPPORTED, or AMBIGUOUS)",
    "confidence": "Number between 0.0 and 1.0",
    "evidence_summary": "String (A short summary of why the question is or is not supported. Cite specific details from the chunks if supported.)",
    "source_chunk_ids": ["Array of Strings (The chunk IDs that provide the support)"],
    "source_pages": ["Array of Integers (The page numbers of the supporting chunks)"]
}

Guidelines for status:
- SUPPORTED: The material contains enough information to fully answer the question.
- PARTIALLY_SUPPORTED: The material contains some relevant information, but not enough to provide a complete answer.
- NOT_SUPPORTED: The material does not contain the information needed to answer the question.
- AMBIGUOUS: The question is unclear or the material is contradictory.

Return ONLY valid JSON. No conversational text."""

    @classmethod
    def validate_question(cls, session: Session, question: QuestionPaperQuestion, study_material_id: str) -> QuestionSupportAnalysis:
        # 1. Search for relevant chunks in the study material
        query = HybridSearchQuery(
            query=question.question_text,
            document_id=study_material_id,
            top_k=5,
            search_mode="hybrid"
        )
        
        search_results = HybridSearchService.execute_search(session, query)
        
        # 2. Prepare the prompt
        chunks_text = ""
        for i, res in enumerate(search_results):
            chunk = res.chunk
            chunks_text += f"\n--- [Chunk ID: {chunk.id}, Page: {chunk.page_number}] ---\n{chunk.content}\n"
            
        user_prompt = f"Question: {question.question_text}\n\nStudy Material Chunks:\n{chunks_text}"
        
        # 3. Call LLM
        try:
            response = default_llm_service.generate_response(
                system_prompt=cls.SYSTEM_PROMPT,
                user_prompt=user_prompt,
                temperature=0.1
            )
            
            cleaned_response = response.strip()
            if cleaned_response.startswith("```json"):
                cleaned_response = cleaned_response[7:]
            if cleaned_response.startswith("```"):
                cleaned_response = cleaned_response[3:]
            if cleaned_response.endswith("```"):
                cleaned_response = cleaned_response[:-3]
                
            analysis_data = json.loads(cleaned_response.strip())
            
            analysis = QuestionSupportAnalysis(
                question_id=question.id,
                study_material_id=study_material_id,
                status=analysis_data.get("status", "AMBIGUOUS"),
                confidence=float(analysis_data.get("confidence", 0.5)),
                evidence_summary=analysis_data.get("evidence_summary", ""),
                source_chunk_ids=analysis_data.get("source_chunk_ids", []),
                source_pages=analysis_data.get("source_pages", [])
            )
            session.add(analysis)
            session.commit()
            return analysis
            
        except Exception as e:
            logger.error(f"Failed to validate question {question.id}: {e}")
            session.rollback()
            analysis = QuestionSupportAnalysis(
                question_id=question.id,
                study_material_id=study_material_id,
                status="AMBIGUOUS",
                confidence=0.0,
                evidence_summary=f"Validation failed due to error: {str(e)}",
                source_chunk_ids=[],
                source_pages=[]
            )
            session.add(analysis)
            session.commit()
            return analysis
            
    @classmethod
    def validate_paper(cls, session: Session, question_paper_id: str, study_material_id: str) -> List[QuestionSupportAnalysis]:
        questions = session.query(QuestionPaperQuestion).filter(QuestionPaperQuestion.document_id == question_paper_id).all()
        results = []
        for q in questions:
            res = cls.validate_question(session, q, study_material_id)
            results.append(res)
        return results
