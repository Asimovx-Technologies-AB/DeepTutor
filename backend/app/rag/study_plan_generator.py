import json
import re
from datetime import datetime
from typing import Dict, List, Optional
from app.rag.ollama_client import ollama
from app.rag.vector_store import vector_store
from app.core import database as db

STUDY_PLAN_PROMPT_TEMPLATE = """You are an expert academic tutor and study planner.
Your goal is to generate a comprehensive, day-by-day study plan based on the provided document context.

Target Exam / Completion Date: {target_date}
Available Days to Study: {total_days} days
Daily Study Time: {hours_per_day} hours/day

Return ONLY valid JSON in this exact structure:
{{
  "title": "A short, motivating title for the study plan",
  "summary": "Brief 1-2 sentence overview of what will be mastered by {target_date}",
  "schedule": [
    {{
      "day": 1,
      "topic": "Main Topic / Module Name for Day 1",
      "focus": "Specific concepts or sections to read & understand",
      "estimated_hours": 2.0,
      "recommended_action": "e.g. Read Chapter 1, take 5-question AI Quiz, review flashcards",
      "key_concepts": ["Concept 1", "Concept 2"]
    }}
  ]
}}

Rules:
- Generate a schedule spanning exactly {total_days} days (Day 1 up to Day {total_days}).
- Spread the document topics logically over the {total_days} days.
- Reserve the final day (Day {total_days}) for full review, final quiz, and practice.
- The schedule MUST be strictly based on the document context below.
- Response MUST contain ONLY valid JSON.

DOCUMENT CONTEXT:
{context}

JSON:"""


async def generate_study_plan(
    user_id: str,
    topic_id: str,
    target_date: str,
    hours_per_day: float = 2.0,
) -> Optional[dict]:
    """
    Analyzes document context for topic_id and generates a structured study plan up to target_date.
    """
    # 1. Calculate remaining days from today until target_date
    today = datetime.utcnow().date()
    try:
        target_dt = datetime.strptime(target_date, "%Y-%m-%d").date()
        total_days = (target_dt - today).days
        if total_days <= 0:
            total_days = 7
    except Exception:
        total_days = 7

    # Cap total_days between 3 and 30 for ideal daily plan granularity
    total_days = max(3, min(30, total_days))

    # 2. Retrieve document text from ChromaDB
    try:
        collection = vector_store._collection(topic_id)
        if collection.count() == 0:
            return None
        data = collection.get(include=["documents"])
        documents = data.get("documents", [])
        if not documents:
            return None
        import random
        shuffled_docs = list(documents)
        random.shuffle(shuffled_docs)
        context = "\n\n".join(shuffled_docs)[:5000]
    except Exception:
        return None

    # 3. Build Prompt & Query Ollama LLM
    prompt = STUDY_PLAN_PROMPT_TEMPLATE.format(
        target_date=target_date,
        total_days=total_days,
        hours_per_day=hours_per_day,
        context=context,
    )

    try:
        messages = [
            {"role": "system", "content": "You are a study plan generator engine that outputs ONLY structured JSON."},
            {"role": "user", "content": prompt},
        ]
        response = await ollama.chat(messages, temperature=0.6)

        json_str = response.strip()
        json_match = re.search(r'\{.*\}', json_str, re.DOTALL)
        if json_match:
            json_str = json_match.group()

        plan_data = json.loads(json_str)

        title = plan_data.get("title", f"Study Plan: {topic_id.capitalize()}")
        schedule = plan_data.get("schedule", [])

        # Ensure valid schedule list
        if not isinstance(schedule, list) or len(schedule) == 0:
            schedule = [
                {
                    "day": i + 1,
                    "topic": f"Day {i + 1} Module Study",
                    "focus": "Key concept review & practice questions",
                    "estimated_hours": hours_per_day,
                    "recommended_action": "Read document & take AI quiz",
                    "key_concepts": ["Core Concept"],
                }
                for i in range(total_days)
            ]

        # 4. Save to database
        plan = db.create_study_plan(
            user_id=user_id,
            topic_id=topic_id,
            title=title,
            target_date=target_date,
            total_days=len(schedule),
            hours_per_day=hours_per_day,
            schedule=schedule,
        )
        return plan

    except Exception as e:
        print(f"Error generating study plan: {e}")
        return None
