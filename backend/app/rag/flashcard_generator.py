"""
AI Flashcards Generator using local Ollama LLM.
Draws context strictly from uploaded document PDFs in ChromaDB or direct disk parsing.
"""
import json
import re
import random
from pathlib import Path
from typing import Dict, List, Optional
from app.rag.ollama_client import ollama
from app.rag.vector_store import vector_store
from app.rag.document_processor import process_document
from app.rag.section_scope import get_section_context, user_owns_section
from app.core import database as db

FLASHCARD_PROMPT_TEMPLATE = """You are a precise academic study engine. Create a deck of exactly 8-10 high-quality study flashcards derived STRICTLY from the provided UPLOADED DOCUMENT CONTEXT.

{topic_instruction}

STRICT MANDATORY RULES:
1. Every flashcard front (question/concept) and back (answer/explanation) MUST be directly supported by the text in the document context.
2. DO NOT include external facts, definitions, or unmentioned topics not explicitly written in the provided document text.
3. If page numbers (e.g., "[Page 12]") appear in the context, include the page citation on the card back.
4. Return ONLY valid JSON matching the exact schema below.

RETURN SCHEMA:
{{
  "flashcards": [
    {{
      "front": "Key term, concept, or question from PDF (concise)",
      "back": "Clear answer, definition, or explanation from PDF [Page X if available]"
    }}
  ]
}}

UPLOADED PDF DOCUMENT CONTEXT:
{context}

JSON:"""


async def generate_flashcards_for_section(
    section_id: str,
    focus_topic: Optional[str] = None,
    user_id: Optional[str] = None,
) -> List[dict]:
    """
    Generate a deck of flashcards derived strictly from the uploaded PDF document text
    stored in the user's specific section.
    """
    context_docs: List[str] = []

    if not user_id or not section_id:
        return []

    if not user_owns_section(user_id, section_id):
        return []

    query_text = focus_topic if (focus_topic and focus_topic.lower() != "all topics (entire pdf)") else None
    context_docs = await get_section_context(
        user_id=user_id,
        section_id=section_id,
        query=query_text,
        top_k=12,
    )

    if not context_docs:
        return []

    # Select representative sample chunks from the section context
    sample_docs = context_docs
    if len(sample_docs) > 15:
        sample_docs = random.sample(sample_docs, 15)

    # Combine document context (capped to avoid LLM context overflow)
    context = "\n\n".join(sample_docs)[:4500]

    topic_instruction = (
        f"FOCUS TOPIC: The flashcards MUST focus specifically on '{focus_topic}' and its core terms/concepts from the PDF."
        if (focus_topic and focus_topic.lower() != "all topics (entire pdf)")
        else "Scope: Comprehensive flashcards covering key terms, definitions, and concepts across the uploaded PDF document section."
    )

    # 3. Call Ollama to generate flashcards strictly from PDF context
    prompt = FLASHCARD_PROMPT_TEMPLATE.format(
        topic_instruction=topic_instruction,
        context=context
    )

    try:
        messages = [
            {
                "role": "system",
                "content": "You are a precise study engine that outputs ONLY structured JSON flashcards derived strictly from provided PDF documents."
            },
            {"role": "user", "content": prompt},
        ]

        response = await ollama.chat(messages, temperature=0.3)

        # Clean and extract JSON string
        json_str = response.strip()
        json_match = re.search(r'\{.*\}', json_str, re.DOTALL)
        if json_match:
            json_str = json_match.group()

        card_data = json.loads(json_str)
        cards = card_data.get("flashcards", [])

        # Delete existing cards for this section to ensure fresh section-derived deck
        db.delete_flashcards_for_topic(section_id)
        if section_id != "general":
            db.delete_flashcards_for_topic("general")

        saved_cards = []
        for c in cards:
            front = c.get("front", "").strip()
            back = c.get("back", "").strip()
            if front and back:
                card = db.add_flashcard(
                    topic_id=section_id,
                    front=front,
                    back=back,
                )
                saved_cards.append(card)

        return saved_cards

    except Exception as e:
        print(f"[flashcard_generator] Error generating flashcards for section {section_id}: {e}")
        return []
