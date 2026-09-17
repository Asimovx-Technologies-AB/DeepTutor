import logging
from typing import Dict, Any, List, Optional
from app.services.llm_service import default_llm_service
from app.schemas.tutoring import QueryUnderstandingResult

logger = logging.getLogger(__name__)

_CLARIFICATION_SYSTEM_PROMPT = """You are DeepTutor's Clarification Generator.

The user's request cannot currently be resolved with sufficient confidence.
Your task is to ask the minimum question required to determine what the user means.

Use ONLY the supplied context.
Do NOT answer the original question.
Do NOT invent possible interpretations.
Do NOT provide unrelated information.
If multiple real candidates exist, mention those candidates.

Keep the question natural and concise.

Examples:
"Which algorithm do you mean: SVM or Decision Tree?"
"Which Question 5 do you mean: SVM Important Questions or Geography Important Questions?"
"Do you mean the CNN architecture or the IoT architecture?"

If the material does not contain the requested topic at all, return "MATERIAL_NOT_SUPPORTED" 
instead of asking a question."""


class ClarificationGenerator:
    """
    Generates concise questions to resolve ambiguity based on current conversation context
    and detected ambiguity types.
    """

    @classmethod
    def generate_clarification(
        cls,
        user_query: str,
        understanding: QueryUnderstandingResult,
        conversation_history: List[Dict[str, str]],
        available_topics: List[str] = None
    ) -> str:
        """
        Generates a specific clarification question using the LLM.
        """
        # If the LLM already generated a clarification prompt during understanding, just use it.
        if understanding.clarification_question:
            return understanding.clarification_question
            
        if understanding.clarification_prompt:
            return understanding.clarification_prompt
            
        context_str = "\n".join([f"{msg.get('role', 'user')}: {msg.get('content', '')}" for msg in conversation_history[-4:]])
        
        prompt = (
            f"Recent Context:\n{context_str}\n\n"
            f"User Query: \"{user_query}\"\n"
            f"Ambiguity Type: {understanding.ambiguity_type}\n"
        )
        
        if available_topics:
            prompt += f"Active Target Candidates: {', '.join(available_topics)}\n"
            
        prompt += "\nGenerate the clarification question to ask the user:"
        
        try:
            resp = default_llm_service.generate(
                prompt=prompt,
                system_prompt=_CLARIFICATION_SYSTEM_PROMPT,
                temperature=0.3
            )
            if resp and "MATERIAL_NOT_SUPPORTED" not in resp:
                return resp.strip().strip('"')
            elif "MATERIAL_NOT_SUPPORTED" in resp:
                return f"I couldn't find '{understanding.topic or user_query}' in the selected study material. Please upload or select the material that covers this topic."
        except Exception as e:
            logger.warning(f"[ClarificationGenerator] Failed to generate clarification: {e}")
            
        return "Could you please clarify what you mean?"
