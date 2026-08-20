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

from app.rag.textbook_reader import is_curriculum_topic, extract_textbook_chunks, get_chapter_title

FLASHCARD_PROMPT_TEMPLATE = """You are an elite academic study engine. Create a deck of 8-10 high-quality, visually structured study flashcards derived STRICTLY from the provided CONTEXT.

{topic_instruction}

STRICT MANDATORY RULES:
1. Every flashcard front (concept/question) and back (explanation) MUST be grounded directly in the provided material.
2. Structure the card back into 3 clean, bite-sized parts:
   - 🎯 **Core Meaning:** 1-2 sentence crystal-clear explanation in plain language.
   - 💡 **Mental Model / Analogy:** One relatable real-world analogy to make the idea click immediately.
   - 🔑 **Key Exam Rule or Formula:** Crucial exam point, SI unit, or LaTeX formula ($...$).
3. Format all math and chemical formulas using clean LaTeX enclosed in single `$...$` (e.g. $a_n = a + (n-1)d$, $1/f = 1/v - 1/u$, $\\text{CO}_2$).
4. Do NOT include bracketed file names or page numbers like [file.pdf p.4] in the card text.
5. Return ONLY valid JSON matching the exact schema below.

RETURN SCHEMA:
{{
  "flashcards": [
    {{
      "front": "✨ Concept Name or Core Question (Concise & Impactful)",
      "back": "🎯 **Core Meaning:** ...\\n\\n💡 **Analogy:** ...\\n\\n🔑 **Exam Tip / Formula:** ..."
    }}
  ]
}}

DOCUMENT CONTEXT:
{context}

JSON:"""


async def generate_flashcards_for_section(
    section_id: str,
    focus_topic: Optional[str] = None,
    user_id: Optional[str] = None,
) -> List[dict]:
    """
    Generate a deck of flashcards derived strictly from textbook context or uploaded PDF document text.
    """
    context_docs: List[str] = []

    if not section_id:
        return []

    # 1. Handle curriculum topics via direct textbook extraction
    if is_curriculum_topic(section_id):
        query_text = focus_topic if (focus_topic and focus_topic.lower() != "all topics (entire pdf)") else None
        context_docs = extract_textbook_chunks(section_id, query=query_text, max_chunks=14)
    else:
        if not user_id or not user_owns_section(user_id, section_id):
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

    sample_docs = context_docs
    if len(sample_docs) > 15:
        sample_docs = random.sample(sample_docs, 15)

    context = "\n\n".join(sample_docs)[:4500]
    chapter_label = get_chapter_title(section_id)

    topic_instruction = (
        f"FOCUS TOPIC: The flashcards MUST focus specifically on '{focus_topic}' from '{chapter_label}'."
        if (focus_topic and focus_topic.lower() != "all topics (entire pdf)")
        else f"Scope: Comprehensive flashcards covering key terms, definitions, formulas, and concepts for '{chapter_label}'."
    )

    prompt = (
        FLASHCARD_PROMPT_TEMPLATE
        .replace("{topic_instruction}", topic_instruction)
        .replace("{context}", context)
    )

    try:
        messages = [
            {
                "role": "system",
                "content": "You are a precise study engine that outputs ONLY structured JSON flashcards derived strictly from provided documents."
            },
            {"role": "user", "content": prompt},
        ]

        response = await ollama.chat(messages, temperature=0.3)

        json_str = response.strip()
        json_match = re.search(r'\{.*\}', json_str, re.DOTALL)
        if json_match:
            json_str = json_match.group()

        card_data = json.loads(json_str)
        cards = card_data.get("flashcards", [])

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
        print(f"[flashcard_generator] LLM call failed, generating from context: {e}")
        cards = []
        for i, doc in enumerate(sample_docs[:8]):
            lines = [l.strip() for l in doc.split("\n") if len(l.strip()) > 25 and not l.startswith("[DIAGRAM")]
            if len(lines) >= 2:
                cards.append({
                    "front": f"💡 {lines[0][:80]}",
                    "back": f"🎯 **Core Meaning:** {lines[1][:180]}\n\n🔑 **Exam Tip:** Remember this key concept from {chapter_label}."
                })
            elif lines:
                cards.append({
                    "front": f"📌 Key Concept: {lines[0][:60]}",
                    "back": f"🎯 **Core Meaning:** {lines[0][:200]}"
                })

        if cards:
            db.delete_flashcards_for_topic(section_id)
            saved_cards = []
            for c in cards:
                card = db.add_flashcard(
                    topic_id=section_id,
                    front=c["front"],
                    back=c["back"],
                )
                saved_cards.append(card)
            return saved_cards
        return []
