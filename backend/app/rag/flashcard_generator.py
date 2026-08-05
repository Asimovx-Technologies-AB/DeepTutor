"""
AI Flashcards Generator using local Ollama LLM.
Draws context from indexed document chunks in ChromaDB.
"""
import json
import re
from typing import Dict, List, Optional
from app.rag.ollama_client import ollama
from app.rag.vector_store import vector_store
from app.core import database as db

FLASHCARD_PROMPT_TEMPLATE = """You are a helpful tutor. Create a deck of exactly 8-10 high-quality flashcards to study key concepts in the provided document context.
{topic_instruction}

Return ONLY valid JSON in this exact structure:
{{
  "flashcards": [
    {{
      "front": "Key concept, question, or term (1 sentence or a single word)",
      "back": "Clear explanation, definition, or answer (1-2 sentences max)"
    }}
  ]
}}

Rules:
- Generate between 8 and 10 cards.
- Keep the fronts and backs concise and easy to review quickly.
- Flashcards must be strictly derived from the facts and information in the context.
- The response MUST contain only the JSON block.

DOCUMENT CONTEXT:
{context}

JSON:"""


async def generate_flashcards_for_topic(
    topic_id: str,
    focus_topic: Optional[str] = None,
) -> List[dict]:
    """
    Generate a deck of flashcards for the given topic using document chunks.
    Saves and returns the generated cards.
    """
    # 1. Fetch text chunks from ChromaDB
    try:
        collection = vector_store._collection(topic_id)
        if collection.count() == 0:
            return []
        
        context_docs = []
        if focus_topic and focus_topic.strip() and focus_topic.lower() != "all topics (entire pdf)":
            try:
                emb = await ollama.get_embedding(focus_topic)
                if emb:
                    search_res = vector_store.search(topic_id, emb, top_k=8)
                    context_docs = [c["text"] for c in search_res if c.get("text")]
            except Exception:
                pass
        
        if not context_docs:
            data = collection.get(include=["documents"])
            documents = data.get("documents", [])
            if not documents:
                return []
            import random
            shuffled_docs = list(documents)
            random.shuffle(shuffled_docs)
            context_docs = shuffled_docs

        context = "\n\n".join(context_docs)[:4000]
    except Exception:
        return []

    topic_instruction = f"FOCUS TOPIC: The flashcards MUST focus specifically on '{focus_topic}' and its core terms/concepts." if (focus_topic and focus_topic.lower() != "all topics (entire pdf)") else "Scope: Comprehensive flashcards covering key terms across the document."

    # 2. Call Ollama to generate flashcards
    prompt = FLASHCARD_PROMPT_TEMPLATE.format(
        topic_instruction=topic_instruction,
        context=context
    )
    
    try:
        messages = [
            {"role": "system", "content": "You are a study card generation engine that outputs ONLY structured JSON."},
            {"role": "user", "content": prompt},
        ]
        
        response = await ollama.chat(messages, temperature=0.7)
        
        # Clean JSON string
        json_str = response.strip()
        json_match = re.search(r'\{.*\}', json_str, re.DOTALL)
        if json_match:
            json_str = json_match.group()
            
        card_data = json.loads(json_str)
        cards = card_data.get("flashcards", [])
        
        # Delete existing flashcards for this topic to generate fresh ones
        db.delete_flashcards_for_topic(topic_id)
            
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
        print(f"Error generating flashcards: {e}")
        return []
