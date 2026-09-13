import random
from typing import Dict, Any


class CasualPipeline:
    """Handles polite conversational greetings and general pleasantries."""

    RESPONSES = [
        "Hello! I am your AI Socratic Tutor. What topic or concept would you like to explore today?",
        "Hi there! Ready to dive into your study material? Ask me anything about your document, formulas, or concepts!",
        "Greetings! I'm here to help you master your subjects step-by-step. What shall we learn today?",
        "You're welcome! Let me know whenever you have another question or doubt to explore.",
    ]

    @classmethod
    def generate_response(cls, query: str) -> Dict[str, Any]:
        lower = query.strip().lower()
        if any(w in lower for w in ["thank", "thanks", "great"]):
            reply = "You're very welcome! Keep up the great studying effort. What would you like to cover next?"
        else:
            reply = random.choice(cls.RESPONSES)

        return {
            "content": reply,
            "intent": "CASUAL",
            "citations": [],
            "grounding_score": 1.0,
            "socratic_follow_up": "Shall we review the core concept or practice with a quick quiz?",
            "suggested_questions": ["Explain the core idea", "Give me a practical example", "Quiz me on this topic"],
        }
