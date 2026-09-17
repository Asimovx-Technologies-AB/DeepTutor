import logging
from typing import Optional, Dict, Any
from app.schemas.tutoring import OutputRequirements

logger = logging.getLogger(__name__)

class OutputComplianceValidator:
    """
    Verifies that generated responses comply with strict user formatting requirements.
    """

    @classmethod
    def validate_response(cls, response: str, requirements: Optional[OutputRequirements]) -> Dict[str, Any]:
        """
        Validates the generated response against output requirements.
        Returns a dictionary indicating if it is compliant and any reasons for non-compliance.
        """
        if not requirements:
            return {"is_compliant": True, "reasons": []}

        reasons = []

        # 1. Format Compliance
        if requirements.format == "ANSWER_ONLY":
            if "### 💡 Interactive Checkpoint" in response or "Here is the answer" in response.lower() or "The answer is" in response.lower():
                reasons.append("Response contains conversational filler or interactive checkpoints when ANSWER_ONLY was requested.")
        elif requirements.format == "BULLETS_ONLY":
            lines = response.split("\n")
            non_bullet_lines = [l for l in lines if l.strip() and not l.strip().startswith(("-", "*", "1.", "2.", "3.", "4.", "5.", "#"))]
            if len(non_bullet_lines) > 2: # Allow a little leeway for title
                reasons.append("Response contains prose paragraphs when BULLETS_ONLY was requested.")
                
        # 2. Length Compliance
        word_count = len(response.split())
        if requirements.length == "SHORT" and word_count > 100:
            reasons.append(f"Response is too long ({word_count} words) for a SHORT requirement.")
            
        # 3. Explanation / Steps / Examples Compliance
        lower_resp = response.lower()
        if not requirements.include_explanation and any(w in lower_resp for w in ["because", "therefore", "meaning that", "this is why", "explanation"]):
            reasons.append("Response appears to include explanation when include_explanation=False.")
            
        if not requirements.include_examples and any(w in lower_resp for w in ["for example", "e.g.", "for instance", "analogy"]):
            reasons.append("Response appears to include examples when include_examples=False.")
            
        if not requirements.include_steps and any(w in lower_resp for w in ["step 1", "step 2", "firstly,"]):
            reasons.append("Response appears to include steps when include_steps=False.")
            
        is_compliant = len(reasons) == 0
        
        return {
            "is_compliant": is_compliant,
            "reasons": reasons
        }
        
    @classmethod
    def enforce_compliance(cls, response: str, requirements: Optional[OutputRequirements], llm_service) -> str:
        """
        If a response is heavily non-compliant, this method attempts to rewrite it using a strict LLM pass.
        For performance, this should only be called if strict mode is critical.
        """
        if not requirements:
            return response
            
        validation = cls.validate_response(response, requirements)
        if validation["is_compliant"]:
            return response
            
        logger.warning(f"Response failed output compliance check: {validation['reasons']}. Rewriting...")
        
        system_prompt = "You are a strict text formatter. Your task is to rewrite the provided text to comply STRICTLY with the requested formatting constraints. Do not add any new information. Do not include conversational filler."
        user_prompt = f"Rewrite the following text to satisfy these constraints:\n"
        user_prompt += f"Format: {requirements.format}\n"
        user_prompt += f"Length: {requirements.length}\n"
        user_prompt += f"Include Explanation: {requirements.include_explanation}\n"
        user_prompt += f"Include Examples: {requirements.include_examples}\n"
        user_prompt += f"Include Steps: {requirements.include_steps}\n\n"
        user_prompt += f"Original Text:\n{response}"
        
        try:
            fixed_response = llm_service.generate_response(system_prompt=system_prompt, user_prompt=user_prompt, temperature=0.1)
            return fixed_response.strip()
        except Exception as e:
            logger.error(f"Failed to rewrite non-compliant response: {e}")
            return response

