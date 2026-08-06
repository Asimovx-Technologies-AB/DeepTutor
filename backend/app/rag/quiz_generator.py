"""
AI Quiz Generator using local Ollama LLM.
Draws context from indexed document chunks in ChromaDB, with smart general knowledge fallback.
"""
import json
import re
from typing import Dict, List, Optional
from app.rag.ollama_client import ollama
from app.rag.vector_store import vector_store
from app.core import database as db

QUIZ_PROMPT_TEMPLATE = """You are an expert educator. Create a multiple choice quiz of exactly {num_questions} questions based on the provided study topic and context.
{topic_instruction}

Return ONLY valid JSON in this exact structure:
{{
  "title": "{title_hint}",
  "questions": [
    {{
      "question_text": "Clear, concise question testing core concepts",
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
- The questions should test key understanding, principles, or concepts.
- The response MUST contain only the JSON block.

STUDY CONTEXT / TOPIC MATERIAL:
{context}

JSON:"""


async def generate_quiz_for_topic(
    topic_id: str,
    focus_topic: Optional[str] = None,
    difficulty: str = "medium",
    time_limit_mins: int = 10,
    num_questions: int = 5,
    user_id: Optional[str] = None,
) -> Optional[dict]:
    """
    Generate a quiz for the given topic using document chunks or general AI knowledge.
    """
    context_docs = []
    
    # 1. Try to find matching collection in ChromaDB
    candidate_keys = []
    if user_id:
        safe_uid = user_id.replace("-", "_")
        safe_tid = (topic_id or "general").replace("-", "_")
        candidate_keys.append(f"{safe_uid}_{safe_tid}")
    candidate_keys.append(topic_id)
    candidate_keys.append("general")

    for ckey in candidate_keys:
        try:
            col = vector_store._collection(ckey)
            if col.count() > 0:
                if focus_topic and focus_topic.strip() and focus_topic.lower() != "all topics (entire pdf)":
                    emb = await ollama.get_embedding(focus_topic)
                    if emb:
                        search_res = vector_store.search(ckey, emb, top_k=8)
                        context_docs = [c["text"] for c in search_res if c.get("text")]
                
                if not context_docs:
                    data = col.get(include=["documents"])
                    docs = data.get("documents", [])
                    if docs:
                        import random
                        shuffled = list(docs)
                        random.shuffle(shuffled)
                        context_docs = shuffled[:6]
                break
        except Exception:
            continue

    # Fallback to general knowledge topic summary if no document collection exists yet
    if context_docs:
        context = "\n\n".join(context_docs)[:4000]
    else:
        topic_name = focus_topic if (focus_topic and focus_topic.lower() != "all topics (entire pdf)") else topic_id.replace("_", " ").title()
        context = f"Subject: {topic_name}. Please test core concepts, fundamental principles, definitions, and key applications related to {topic_name}."

    topic_instruction = (
        f"FOCUS TOPIC: The quiz MUST focus specifically on '{focus_topic}'."
        if (focus_topic and focus_topic.lower() != "all topics (entire pdf)")
        else f"Scope: Comprehensive quiz on {topic_id.replace('_', ' ').title()}."
    )
    title_hint = (
        f"Quiz: {focus_topic}"
        if (focus_topic and focus_topic.lower() != "all topics (entire pdf)")
        else f"Quiz: {topic_id.replace('_', ' ').title()}"
    )

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
        
        json_str = response.strip()
        cleaned = re.sub(r'```(?:json)?\s*', '', json_str, flags=re.IGNORECASE)
        cleaned = re.sub(r'```', '', cleaned).strip()
        json_match = re.search(r'\{.*\}', cleaned, re.DOTALL)
        if json_match:
            cleaned = json_match.group()
        cleaned = re.sub(r',\s*([}\]])', r'\1', cleaned)
        
        try:
            quiz_data = json.loads(cleaned)
        except Exception:
            quiz_data = {"title": title_hint, "questions": []}
        
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
