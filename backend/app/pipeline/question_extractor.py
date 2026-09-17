import json
import logging
from typing import List, Dict, Any
from sqlalchemy.orm import Session
from app.models.question_paper import QuestionPaperQuestion
from app.services.llm_service import default_llm_service

logger = logging.getLogger(__name__)

class QuestionPaperExtractor:
    """
    Extracts individual questions from a question paper document using an LLM.
    """
    
    SYSTEM_PROMPT = """You are an expert academic parser. Your task is to extract individual questions from the provided question paper text.
    Return ONLY a valid JSON array of objects, where each object represents a question with the following schema:
    [
      {
        "question_number": "String (e.g. '1', '1a', 'Q2')",
        "question_text": "String (The full text of the question)",
        "section": "String or null (e.g. 'Section A', 'Part 1')",
        "marks": "Number or null (The marks allocated for the question)",
        "source_page": "Integer (The page number where the question starts, based on the provided text markers)",
        "topics": ["Array of Strings (Inferred topics tested by this question)"]
      }
    ]
    Do not include any conversational text, markdown formatting blocks (like ```json), or explanations outside the JSON array.
    """

    @classmethod
    def extract_questions(cls, session: Session, doc_id: str, pages_data: List[Dict[str, Any]]) -> List[QuestionPaperQuestion]:
        """
        Parses pages_data to extract questions and saves them to the database.
        """
        # Combine text with page markers
        full_text = ""
        for page in pages_data:
            page_num = page.get("page_number", 1)
            text = page.get("normalized_text", "") or page.get("raw_text", "")
            full_text += f"\n--- [PAGE {page_num}] ---\n{text}\n"
            
        # Process in chunks to respect context limits
        max_chars = 40000 
        chunks = [full_text[i:i+max_chars] for i in range(0, len(full_text), max_chars)]
        
        extracted_db_questions = []
        
        for chunk in chunks:
            if len(chunk.strip()) < 50:
                continue
                
            try:
                response = default_llm_service.generate_response(
                    system_prompt=cls.SYSTEM_PROMPT,
                    user_prompt=f"Extract questions from the following text:\n\n{chunk}",
                    temperature=0.1
                )
                
                # Cleanup JSON
                cleaned_response = response.strip()
                if cleaned_response.startswith("```json"):
                    cleaned_response = cleaned_response[7:]
                if cleaned_response.startswith("```"):
                    cleaned_response = cleaned_response[3:]
                if cleaned_response.endswith("```"):
                    cleaned_response = cleaned_response[:-3]
                    
                questions_data = json.loads(cleaned_response.strip())
                
                if isinstance(questions_data, list):
                    for q_data in questions_data:
                        try:
                            marks = float(q_data.get("marks")) if q_data.get("marks") is not None else None
                        except (ValueError, TypeError):
                            marks = None
                            
                        try:
                            source_page = int(q_data.get("source_page")) if q_data.get("source_page") else None
                        except (ValueError, TypeError):
                            source_page = None
                            
                        q_obj = QuestionPaperQuestion(
                            document_id=doc_id,
                            question_number=q_data.get("question_number"),
                            question_text=q_data.get("question_text", ""),
                            section=q_data.get("section"),
                            marks=marks,
                            source_page=source_page,
                            topics=q_data.get("topics", [])
                        )
                        session.add(q_obj)
                        extracted_db_questions.append(q_obj)
                        
            except json.JSONDecodeError as e:
                logger.error(f"Failed to decode LLM response for question extraction: {e}")
            except Exception as e:
                logger.error(f"Error during question extraction: {e}")
                
        session.commit()
        return extracted_db_questions
