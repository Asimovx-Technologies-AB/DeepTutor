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


async def generate_flashcards_for_topic(
    topic_id: str,
    focus_topic: Optional[str] = None,
    user_id: Optional[str] = None,
) -> List[dict]:
    """
    Generate a deck of flashcards derived strictly from the uploaded PDF document text.
    Saves and returns the generated cards.
    """
    context_docs: List[str] = []

    # 1. Prioritize reading directly from the user's uploaded PDF document(s)
    user_docs: List[dict] = []
    if user_id:
        user_docs = db.get_documents_for_user(user_id)
    if not user_docs and topic_id:
        user_docs = db.get_documents_for_topic(topic_id)
    if not user_docs:
        user_docs = db.get_documents_for_topic("general")

    for d in user_docs:
        fpath = d.get("file_path")
        if fpath and Path(fpath).exists():
            try:
                chunks = process_document(fpath)
                fname = d.get("file_name", "Document")
                for c in chunks:
                    if c.get("text"):
                        page = c.get("metadata", {}).get("page", 1)
                        context_docs.append(f"[{fname} Page {page}] {c['text']}")
            except Exception as e:
                print(f"Error parsing uploaded document {fpath}: {e}")

    # 2. Fallback to vector store lookup across candidate collections if direct files return no text
    if not context_docs:
        candidate_topics = []
        if user_id:
            safe_uid = user_id.replace("-", "_")
            safe_tid = (topic_id or "general").replace("-", "_")
            candidate_topics.append(f"{safe_uid}_{safe_tid}")
        if topic_id:
            candidate_topics.append(topic_id)
        candidate_topics.append("general")

        for tid in candidate_topics:
            try:
                collection = vector_store._collection(tid)
                if collection.count() == 0:
                    continue

                if focus_topic and focus_topic.strip() and focus_topic.lower() != "all topics (entire pdf)":
                    try:
                        emb = await ollama.get_embedding(focus_topic)
                        if emb:
                            search_res = vector_store.search(tid, emb, top_k=10)
                            context_docs = [
                                f"[Page {c.get('page', 1)}] {c['text']}" for c in search_res if c.get("text")
                            ]
                    except Exception:
                        pass

                if not context_docs:
                    data = collection.get(include=["documents", "metadatas"])
                    documents = data.get("documents", [])
                    metadatas = data.get("metadatas", [])
                    if documents:
                        doc_pairs = list(zip(documents, metadatas if metadatas else [{}] * len(documents)))
                        random.shuffle(doc_pairs)
                        for text, meta in doc_pairs[:12]:
                            page = meta.get("page", 1) if meta else 1
                            context_docs.append(f"[Page {page}] {text}")

                if context_docs:
                    break
            except Exception:
                continue

    if not context_docs:
        return []

    # Select representative sample chunks from the document context
    sample_docs = context_docs
    if len(sample_docs) > 15:
        sample_docs = random.sample(sample_docs, 15)

    # Combine document context (capped to avoid LLM context overflow)
    context = "\n\n".join(sample_docs)[:4500]

    topic_instruction = (
        f"FOCUS TOPIC: The flashcards MUST focus specifically on '{focus_topic}' and its core terms/concepts from the PDF."
        if (focus_topic and focus_topic.lower() != "all topics (entire pdf)")
        else "Scope: Comprehensive flashcards covering key terms, definitions, and concepts across the uploaded PDF document."
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

        # Delete existing cards for this topic to ensure fresh PDF-derived deck
        db.delete_flashcards_for_topic(topic_id)
        if topic_id != "general":
            db.delete_flashcards_for_topic("general")

        saved_cards = []
        for c in cards:
            front = c.get("front", "").strip()
            back = c.get("back", "").strip()
            if front and back:
                card = db.add_flashcard(
                    topic_id=topic_id,
                    front=front,
                    back=back,
                )
                saved_cards.append(card)

        return saved_cards

    except Exception as e:
        print(f"Error generating flashcards from PDF: {e}")
        return []
