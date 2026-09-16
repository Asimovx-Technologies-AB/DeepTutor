import random
from typing import Dict, Any


class CasualPipeline:
    """Handles polite conversational greetings, pleasantries, and acknowledgments."""

    RESPONSES = [
        "Hello! I am your AI Socratic Tutor. What topic or concept would you like to explore today?",
        "Hi there! Ready to dive into your study material? Ask me anything about your document, formulas, or concepts!",
        "Greetings! I'm here to help you master your subjects step-by-step. What shall we learn today?",
        "You're very welcome! Let me know whenever you have another question or concept to explore.",
    ]

    @classmethod
    def generate_response(cls, query: str) -> Dict[str, Any]:
        lower = query.strip().lower()
        if any(w in lower for w in ["thank", "thanks", "great", "awesome", "cool", "got it", "makes sense", "understood"]):
            reply = "You're very welcome! Let me know whenever you're ready to explore another concept or practice more questions."
        elif any(w in lower for w in ["bye", "goodbye", "good night", "see you"]):
            reply = "Goodbye! Best of luck with your studies. I'll be here whenever you're ready to learn more."
        else:
            reply = random.choice(cls.RESPONSES)

        return {
            "content": reply,
            "intent": "CASUAL",
            "citations": [],
            "grounding_score": 1.0,
            "socratic_follow_up": "What concept or chapter would you like to explore next?",
            "suggested_questions": ["Explain the core idea", "Give me 5 practice questions", "Summary of the whole material"],
        }
