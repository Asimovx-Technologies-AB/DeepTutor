import json
import re
import random
from pathlib import Path
from typing import Dict, List, Optional
from app.rag.gemini_client import gemini_client
from app.rag.ollama_client import ollama
from app.rag.vector_store import vector_store
from app.rag.document_processor import process_document
from app.rag.section_scope import get_section_context, user_owns_section
from app.core import database as db

from app.rag.textbook_reader import is_curriculum_topic, extract_textbook_chunks, get_chapter_title

FLASHCARD_PROMPT_TEMPLATE = """You are an elite academic study engine and Kerala SCERT / CBSE Board Exam Specialist. 
Create a deck of 8-10 high-quality, point-by-point study flashcards derived STRICTLY from the provided CONTEXT.

{topic_instruction}

STRICT MANDATORY RULES FOR CARD BACK (MUST BE POINT-BY-POINT):
1. The back of each card MUST be strictly formatted in clean, concise, point-by-point bullet points (•). NEVER write long, dense paragraphs.
2. Structure the card back into clean, bite-sized point-by-point bullets:
   • 📌 **Core Concept:** 1-2 short bullet lines explaining the main definition in simple English.
   • 💡 **Real-Life Analogy / Mental Model:** 1 quick real-world comparison to remember it easily.
   • 📐 **Formula / Law:** Standard equation in LaTeX ($...$) with variable definitions. (Omit if not applicable).
   • ⚠️ **Exam Trap & Key Fact:** 1 crucial exam trap to avoid or landmark point for marks.
3. Every single point on the back must start with a bullet symbol (•) or an emoji bullet (📌, 💡, 📐, ⚠️).
4. Format all math and chemical formulas using clean LaTeX enclosed in single `$...$` (e.g. $a_n = a + (n-1)d$, $\\text{CO}_2$).
5. Do NOT include bracketed file names or page numbers like [file.pdf p.4] in the card text.
6. Return ONLY valid JSON matching the exact schema below.

RETURN SCHEMA:
{{
  "flashcards": [
    {{
      "front": "✨ Concept Name or Core Question (Concise & Impactful)",
      "back": "• 📌 **Core Concept:** Direct point-by-point summary.\\n• 💡 **Analogy:** Quick real-world picture.\\n• 📐 **Formula:** $...$\\n• ⚠️ **Key Exam Point:** Crucial rule for scoring full marks."
    }}
  ]
}}

DOCUMENT CONTEXT:
{context}

JSON:"""


def format_card_back(back_text: str) -> str:
    if not back_text:
        return ""
    cleaned = back_text.strip()
    # Normalize inline bullets and glued emoji headers into separate bullet lines
    cleaned = re.sub(r'\s*[•●*]\s*', '\n\n• ', cleaned)
    cleaned = re.sub(r'([^\n])\s*(📌|💡|📐|⚠️|🎯|🔹|🔸|⚡)', r'\1\n\n• \2', cleaned)
    lines = [l.strip() for l in cleaned.split('\n') if l.strip()]
    formatted_lines = []
    for l in lines:
        if not l.startswith('•') and not l.startswith('-'):
            l = f"• {l}"
        formatted_lines.append(l)
    return "\n\n".join(formatted_lines)


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

    card_data = None
    messages = [
        {
            "role": "system",
            "content": "You are a precise study engine that outputs ONLY structured JSON flashcards with point-by-point bullet backs derived strictly from provided documents."
        },
        {"role": "user", "content": prompt},
    ]

    # 1. Primary Generation: Gemini API
    if await gemini_client.is_available():
        try:
            print(f"[flashcard_generator] Calling Gemini for flashcards ({chapter_label})...")
            gemini_resp = await gemini_client.chat(messages, temperature=0.25)
            json_str = gemini_resp.strip()
            json_str = re.sub(r'```(?:json)?\s*', '', json_str, flags=re.IGNORECASE)
            json_str = re.sub(r'```', '', json_str).strip()
            json_match = re.search(r'\{.*\}', json_str, re.DOTALL)
            if json_match:
                json_str = json_match.group()
            json_str = re.sub(r',\s*([}\]])', r'\1', json_str)
            card_data = json.loads(json_str)
        except Exception as e:
            print(f"[flashcard_generator] Gemini flashcard generation warning: {e}")

    # 2. Secondary Generation: Ollama
    if not card_data or not card_data.get("flashcards"):
        try:
            print(f"[flashcard_generator] Calling Ollama for flashcards ({chapter_label})...")
            response = await ollama.chat(messages, temperature=0.3)
            json_str = response.strip()
            json_str = re.sub(r'```(?:json)?\s*', '', json_str, flags=re.IGNORECASE)
            json_str = re.sub(r'```', '', json_str).strip()
            json_match = re.search(r'\{.*\}', json_str, re.DOTALL)
            if json_match:
                json_str = json_match.group()
            json_str = re.sub(r',\s*([}\]])', r'\1', json_str)
            card_data = json.loads(json_str)
        except Exception as e:
            print(f"[flashcard_generator] Ollama flashcard generation warning: {e}")

    if card_data and card_data.get("flashcards"):
        cards = card_data.get("flashcards", [])
        db.delete_flashcards_for_topic(section_id)
        if section_id != "general":
            db.delete_flashcards_for_topic("general")

        saved_cards = []
        for c in cards:
            front = c.get("front", "").strip()
            back = format_card_back(c.get("back", ""))
            if front and back:
                card = db.add_flashcard(
                    topic_id=section_id,
                    front=front,
                    back=back,
                )
                saved_cards.append(card)

        if saved_cards:
            return saved_cards

    # 3. Fallback Generation from Context Docs
    print(f"[flashcard_generator] Generating fallback point-by-point cards from context for {section_id}...")
    cards = []
    for i, doc in enumerate(sample_docs[:8]):
        lines = [l.strip() for l in doc.split("\n") if len(l.strip()) > 25 and not l.startswith("[DIAGRAM")]
        if len(lines) >= 2:
            cards.append({
                "front": f"💡 {lines[0][:80]}",
                "back": f"• 📌 **Core Concept:** {lines[1][:180]}\n• 💡 **Key Takeaway:** Essential principle for {chapter_label}\n• ⚠️ **Exam Point:** Remember to write full steps and standard units."
            })
        elif lines:
            cards.append({
                "front": f"📌 Key Concept: {lines[0][:60]}",
                "back": f"• 📌 **Core Concept:** {lines[0][:200]}\n• ⚠️ **Exam Point:** Core definition tested in Kerala SSLC & CBSE exams."
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
