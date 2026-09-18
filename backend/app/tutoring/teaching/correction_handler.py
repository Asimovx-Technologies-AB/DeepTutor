import re
import logging
from typing import Dict, Any, List, Optional, Tuple
from app.services.llm_service import default_llm_service

logger = logging.getLogger(__name__)

_CORRECTION_SYSTEM_PROMPT = """You are DeepTutor, an expert AI Academic Tutor and Teacher.
The student has stated that your previous explanation or answer was wrong or incorrect (e.g. "wrong", "wrong answer", "that's wrong", "incorrect", "no", "not correct", "this is wrong").

YOUR TASK:
1. Thoroughly recheck the previous AI response against the conversation context, verified facts, and study material.
2. Determine objectively whether the previous AI answer actually contained an error, or whether it was correct and the student has a misconception:
   - NEVER blindly agree with the student's assertion if the previous answer was factually correct.
   - NEVER blindly reject the student's feedback if the previous answer indeed made a mistake.
3. If the previous answer had an error:
   - Explicitly acknowledge the mistake using a natural teacher voice:
     "The previous explanation had an error. Here is the corrected version..." or "You are right to point that out. The previous explanation had a mistake..."
   - Identify precisely what was incorrect.
   - Provide the corrected version.
   - Give a short, clear explanation of WHY the corrected answer is right.
   - DO NOT repeat the entire previous explanation when only a small correction is required; keep your response focused directly on the correction.
4. If the previous answer was actually correct:
   - Warmly explain why the previous answer is valid:
     "I rechecked our previous explanation, and it is actually correct because..."
   - Clarify the likely reason for confusion or misconception.
5. Conclude naturally to keep the dialogue going:
   - In Teacher Mode: conclude with "**Would you like me to continue to the next subtopic?**"
   - In General Chat: conclude with a natural, engaging follow-up question.

RULES:
- Natural, encouraging, academic teacher tone.
- Concise and focused on the correction.
- Work across all subjects (science, math, literature, history, computer science, etc.).
- Clean Markdown formatting (LaTeX $...$ for math if applicable)."""

_STATEMENT_EVALUATOR_SYSTEM_PROMPT = """You are DeepTutor, an expert AI Academic Tutor and Teacher.
The student has stated a factual or conceptual claim in relation to the current topic and previous conversation.

YOUR TASK:
Analyze the student's statement carefully:
1. If the statement is INCORRECT:
   - Clearly tell the user that it is incorrect and provide the correct information.
   - Use natural teacher phrasing: "That is not correct. The correct answer is..."
   - Briefly explain why.
2. If the statement is PARTIALLY CORRECT:
   - Explain what part is correct and what part needs correction.
   - Use natural teacher phrasing: "You're close, but there is one mistake..."
3. If the statement is FULLY CORRECT:
   - Acknowledge it warmly and affirm their understanding.
   - Use natural teacher phrasing: "Yes, that's correct. Let's continue..."
4. If the meaning is AMBIGUOUS:
   - Ask a concise clarification question instead of making assumptions.

RULES:
- NEVER blindly agree with the student.
- NEVER blindly reject the student.
- Always use the previous conversation context and verified subject domain knowledge.
- Keep the response focused and concise.
- In Teacher Mode: conclude with "**Would you like me to continue to the next subtopic?**"
- In General Chat: continue the learning flow naturally."""


class TeachingCorrectionHandler:
    """
    Handles student feedback/corrections about prior AI answers and evaluates student factual statements.
    """

    @classmethod
    def handle_user_correction(
        cls,
        user_feedback: str,
        conversation_history: List[Dict[str, Any]],
        current_topic: Optional[str] = None,
        current_subtopic: Optional[str] = None,
        study_material_snippets: Optional[List[str]] = None,
        is_teacher_mode: bool = False,
    ) -> str:
        """
        Rechecks the previous AI answer, identifies inaccuracies, and outputs a focused correction.
        """
        # Find the last assistant message
        last_ai_message = ""
        for msg in reversed(conversation_history):
            if msg.get("role") == "assistant":
                last_ai_message = msg.get("content", "")
                break

        context_blocks = []
        for msg in conversation_history[-4:]:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            context_blocks.append(f"{role.upper()}: {content}")

        history_str = "\n\n".join(context_blocks)
        material_str = "\n\n".join(study_material_snippets[:4]) if study_material_snippets else "None provided"

        prompt = (
            f"Topic: {current_topic or 'Academic Study'}\n"
            f"Active Subtopic: {current_subtopic or 'Current Concept'}\n\n"
            f"--- VERIFIED STUDY MATERIAL ---\n{material_str}\n\n"
            f"--- RECENT CONVERSATION CONTEXT ---\n{history_str}\n\n"
            f"--- PREVIOUS AI EXPLANATION TO RECHECK ---\n{last_ai_message}\n\n"
            f"--- STUDENT FEEDBACK ---\n\"{user_feedback}\"\n\n"
            f"Mode: {'Teacher Mode (progressive subtopics)' if is_teacher_mode else 'General Study Chat'}\n\n"
            f"Evaluate the previous AI answer against the student feedback and produce the teacher correction response:"
        )

        try:
            resp = default_llm_service.generate(
                prompt=prompt,
                system_prompt=_CORRECTION_SYSTEM_PROMPT,
            )
            if resp and len(resp.strip()) > 20:
                clean = resp.strip()
                if is_teacher_mode and "continue to the next subtopic" not in clean.lower():
                    clean += "\n\n**Would you like me to continue to the next subtopic?**"
                return clean
        except Exception as e:
            logger.error(f"[TeachingCorrectionHandler] Correction generation failed: {e}")

        # Deterministic pedagogical fallback
        if is_teacher_mode:
            return (
                f"The previous explanation had an error. Here is the corrected version regarding **{current_subtopic or current_topic or 'this concept'}**:\n\n"
                f"Thank you for pointing that out. Let's make sure this detail is completely accurate before moving forward.\n\n"
                f"**Would you like me to continue to the next subtopic?**"
            )
        return (
            f"The previous explanation had an error. Here is the corrected version:\n\n"
            f"Thank you for catching that. Let's ensure this is completely clear. What aspect would you like to explore next?"
        )

    @classmethod
    def handle_statement_evaluation(
        cls,
        user_statement: str,
        conversation_history: List[Dict[str, Any]],
        current_topic: Optional[str] = None,
        current_subtopic: Optional[str] = None,
        study_material_snippets: Optional[List[str]] = None,
        is_teacher_mode: bool = False,
    ) -> str:
        """
        Evaluates student factual statement for correctness and provides teacher feedback.
        """
        context_blocks = []
        for msg in conversation_history[-4:]:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            context_blocks.append(f"{role.upper()}: {content}")

        history_str = "\n\n".join(context_blocks)
        material_str = "\n\n".join(study_material_snippets[:4]) if study_material_snippets else "None provided"

        prompt = (
            f"Topic: {current_topic or 'Academic Study'}\n"
            f"Active Subtopic: {current_subtopic or 'Current Concept'}\n\n"
            f"--- VERIFIED STUDY MATERIAL ---\n{material_str}\n\n"
            f"--- RECENT CONVERSATION CONTEXT ---\n{history_str}\n\n"
            f"--- STUDENT STATEMENT TO EVALUATE ---\n\"{user_statement}\"\n\n"
            f"Mode: {'Teacher Mode (progressive subtopics)' if is_teacher_mode else 'General Study Chat'}\n\n"
            f"Evaluate the student's statement and respond with appropriate teacher feedback:"
        )

        try:
            resp = default_llm_service.generate(
                prompt=prompt,
                system_prompt=_STATEMENT_EVALUATOR_SYSTEM_PROMPT,
            )
            if resp and len(resp.strip()) > 20:
                clean = resp.strip()
                if is_teacher_mode and "continue to the next subtopic" not in clean.lower():
                    clean += "\n\n**Would you like me to continue to the next subtopic?**"
                return clean
        except Exception as e:
            logger.error(f"[TeachingCorrectionHandler] Statement evaluation failed: {e}")

        # Deterministic fallback
        if is_teacher_mode:
            return (
                f"You're exploring a key aspect of **{current_subtopic or current_topic or 'this concept'}**.\n\n"
                f"Let's review this together against our study material to make sure our foundations are 100% solid.\n\n"
                f"**Would you like me to continue to the next subtopic?**"
            )
        return (
            f"That's a good observation regarding **{current_topic or 'this topic'}**.\n\n"
            f"Let's verify how this connects with the rest of your course material. What would you like to explore next?"
        )
