import logging
from typing import List
from sqlalchemy.orm import Session
from app.models.question_paper import QuestionPaperQuestion, QuestionSupportAnalysis
from app.models.chunk import KnowledgeChunk
from app.services.llm_service import default_llm_service

logger = logging.getLogger(__name__)

class StudyNotesGenerator:
    """
    Generates targeted study notes based on Question Papers and their mapping to Study Materials.
    """

    SYSTEM_PROMPT = """You are an elite academic tutor creating high-yield, publication-grade Study Notes.
Your task is to synthesize the provided study material excerpts into targeted revision notes that directly answer the core themes of the exam questions.

=== PUBLICATION-GRADE STUDY NOTES CONTRACT ===
1. Structure your notes with clear Markdown headers (e.g., `#`, `##`).
2. Include an 'Executive Overview' (2-3 concise sentences).
3. Group related concepts logically based on the provided questions and chunks.
4. Bold key terms and provide rigorous definitions.
5. Include essential formulas or principles if applicable, using clean LaTeX (`$$...$$` or `$ ... $`).
6. Do NOT invent information outside the provided text.
7. NEVER output conversational filler like "Here are your notes:".

Output ONLY the beautifully formatted Markdown study notes.
"""

    @classmethod
    def generate_question_paper_notes(cls, session: Session, question_paper_id: str, study_material_id: str) -> str:
        """
        Generates study notes focused on the topics tested in a question paper,
        using only the material from the provided study_material_id.
        """
        # 1. Fetch Question Support Analysis
        analyses = session.query(QuestionSupportAnalysis).filter(
            QuestionSupportAnalysis.study_material_id == study_material_id
        ).join(
            QuestionPaperQuestion, QuestionSupportAnalysis.question_id == QuestionPaperQuestion.id
        ).filter(
            QuestionPaperQuestion.document_id == question_paper_id
        ).all()
        
        if not analyses:
            return "No mapped questions found between this Question Paper and Study Material. Please run the validation step first."
            
        supported_analyses = [a for a in analyses if a.status in ("SUPPORTED", "PARTIALLY_SUPPORTED")]
        
        if not supported_analyses:
            return "None of the questions in this Question Paper appear to be supported by the provided Study Material."
            
        # 2. Gather unique supporting chunk IDs
        chunk_ids = set()
        for analysis in supported_analyses:
            if analysis.source_chunk_ids:
                chunk_ids.update(analysis.source_chunk_ids)
                
        if not chunk_ids:
            return "No supporting excerpts were found in the study material."
            
        # 3. Fetch the actual chunks
        chunks = session.query(KnowledgeChunk).filter(KnowledgeChunk.id.in_(list(chunk_ids))).all()
        
        # 4. Fetch the questions to provide context
        questions_map = {}
        for analysis in supported_analyses:
            q = session.query(QuestionPaperQuestion).filter(QuestionPaperQuestion.id == analysis.question_id).first()
            if q:
                questions_map[q.id] = q.question_text
                
        # 5. Build prompt
        prompt_parts = ["=== TARGET EXAM QUESTIONS ==="]
        for idx, (qid, q_text) in enumerate(questions_map.items(), 1):
            prompt_parts.append(f"Q{idx}: {q_text}")
            
        prompt_parts.append("\n=== SUPPORTING STUDY MATERIAL EXCERPTS ===")
        for i, chunk in enumerate(chunks, 1):
            sec = f" (Section: {chunk.chapter_section})" if chunk.chapter_section else ""
            prompt_parts.append(f"--- Excerpt {i}{sec} ---\n{chunk.content}")
            
        user_prompt = "\n".join(prompt_parts)
        
        # 6. Generate notes
        try:
            response = default_llm_service.generate_response(
                system_prompt=cls.SYSTEM_PROMPT,
                user_prompt=user_prompt,
                temperature=0.3
            )
            return response.strip()
        except Exception as e:
            logger.error(f"Failed to generate study notes: {e}")
            return f"Failed to generate study notes due to an internal error: {str(e)}"
