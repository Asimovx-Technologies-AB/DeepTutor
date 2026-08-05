"""
AI Quiz Generator using local Ollama LLM.
Draws context from indexed document chunks in ChromaDB.
"""
import json
import re
from typing import Dict, List, Optional
from app.rag.ollama_client import ollama
from app.rag.vector_store import vector_store
from app.core import database as db

QUIZ_PROMPT_TEMPLATE = """You are an expert educator. Create a multiple choice quiz of exactly {num_questions} questions based on the provided document context.
{topic_instruction}

Return ONLY valid JSON in this exact structure:
{{
  "title": "{title_hint}",
  "questions": [
    {{
      "question_text": "Clear, concise question based on the text",
      "options": [
        "First option",
        "Second option",
        "Third option",
        "Fourth option"
      ],
      "correct_answer": "A",
      "explanation": "Detailed explanation of why this option is correct"
    }}
  ]
}}

Rules:
- Generate exactly {num_questions} questions.
- Each question must have exactly 4 options.
- The "correct_answer" must be one of: "A", "B", "C", "D".
- The questions should test understanding, facts, or concepts directly found in the context.
- The response MUST contain only the JSON block.

DOCUMENT CONTEXT:
{context}

JSON:"""


async def generate_quiz_for_topic(
    topic_id: str,
    focus_topic: Optional[str] = None,
    difficulty: str = "medium",
    time_limit_mins: int = 10,
    num_questions: int = 5,
) -> Optional[dict]:
    """
    Generate a quiz for the given topic using document chunks.
    Saves and returns the generated quiz dict.
    """
    # 1. Fetch text chunks from ChromaDB
    try:
        collection = vector_store._collection(topic_id)
        if collection.count() == 0:
            return None
        
        context_docs = []
        if focus_topic and focus_topic.strip() and focus_topic.lower() != "all topics (entire pdf)":
            # Target chunks matching the specific focus topic via embedding search
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
                return None
            import random
            shuffled_docs = list(documents)
            random.shuffle(shuffled_docs)
            context_docs = shuffled_docs

        context = "\n\n".join(context_docs)[:4000]
    except Exception:
        return None

    topic_instruction = f"FOCUS TOPIC: The quiz MUST focus specifically on '{focus_topic}' and its related concepts." if (focus_topic and focus_topic.lower() != "all topics (entire pdf)") else "Scope: Comprehensive quiz covering all main topics across the document."
    title_hint = f"Quiz: {focus_topic}" if (focus_topic and focus_topic.lower() != "all topics (entire pdf)") else "Comprehensive Quiz: All Topics"

    # 2. Call Ollama to generate quiz
    prompt = QUIZ_PROMPT_TEMPLATE.format(
        num_questions=num_questions,
        topic_instruction=topic_instruction,
        title_hint=title_hint,
        context=context
    )
    
    try:
        messages = [
            {"role": "system", "content": "You are a quiz generation engine that outputs ONLY structured JSON."},
            {"role": "user", "content": prompt},
        ]
        
        response = await ollama.chat(messages, temperature=0.7)
        
        # Clean JSON string
        json_str = response.strip()
        json_match = re.search(r'\{.*\}', json_str, re.DOTALL)
        if json_match:
            json_str = json_match.group()
            
        quiz_data = json.loads(json_str)
        
        # 3. Save to database
        title = quiz_data.get("title", title_hint)
        quiz = db.create_quiz(
            topic_id=topic_id,
            title=title,
            difficulty=difficulty,
            time_limit=time_limit_mins,
        )
        
        for q in quiz_data.get("questions", []):
            options = q.get("options", [])
            # Pad options if less than 4
            while len(options) < 4:
                options.append(f"Option {len(options) + 1}")
            options = options[:4]
            
            db.add_question(
                quiz_id=quiz["id"],
                question_text=q.get("question_text", ""),
                question_type="multiple_choice",
                options=options,
                correct_answer=q.get("correct_answer", "A").upper(),
                explanation=q.get("explanation", ""),
            )
            
        return db.get_quiz(quiz["id"])
        
    except Exception as e:
        print(f"Error generating quiz: {e}")
        return None
