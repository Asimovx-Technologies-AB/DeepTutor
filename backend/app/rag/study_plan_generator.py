import json
import re
import random
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional
from app.rag.ollama_client import ollama
from app.rag.vector_store import vector_store
from app.rag.document_processor import process_document
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
      "estimated_hours": {hours_per_day},
      "recommended_action": "Read Chapter 1, review AI Study Notes",
      "key_concepts": ["Concept 1", "Concept 2"],
      "study_notes": "Key study notes & core takeaways for Day 1 concept..."
    }}
  ]
}}

Rules:
- Generate a schedule spanning exactly {total_days} days (Day 1 up to Day {total_days}).
- Spread the document topics logically over the {total_days} days.
- Reserve the final day (Day {total_days}) for full review, final quiz, and practice.
- Include a concise 2-3 sentence 'study_notes' summary for each day topic.
- The schedule MUST be strictly based on the document context below.
- Response MUST contain ONLY valid JSON. No conversational commentary.

DOCUMENT CONTEXT:
{context}

JSON:"""


DAY_NOTES_PROMPT_TEMPLATE = """You are an expert academic tutor. Generate comprehensive, structured, easy-to-study notes for a student studying the topic below from their uploaded textbook PDF.

DAY TOPIC: {day_topic}
KEY CONCEPTS: {key_concepts}

DOCUMENT CONTEXT:
{context}

Format your response strictly using clean, beautiful Markdown with the following structure:

# 📌 {day_topic} — Study Notes

## 💡 Overview & Core Objectives
[Clear 2-3 sentence overview of this topic]

## 🔑 Key Definitions & Terms
- **Concept 1**: Clear explanation and definition from PDF.
- **Concept 2**: Clear explanation and definition from PDF.
- **Concept 3**: Clear explanation and definition from PDF.

## 📝 In-Depth Breakdown & Formulae / Rules
- **Core Principle**: Step-by-step breakdown of how this works.
- **Key Takeaways**: Essential points to remember for exams.

## 🎯 Quick Self-Check Review
1. **Q**: [Practice question on this topic]
   **A**: [Short answer]
2. **Q**: [Practice question on this topic]
   **A**: [Short answer]
"""


def _clean_and_parse_json(text: str) -> Optional[dict]:
    """Robust JSON extraction & repair helper for LLM responses."""
    if not text:
        return None

    # 1. Remove markdown fences e.g. ```json ... ```
    cleaned = re.sub(r'```(?:json)?\s*', '', text, flags=re.IGNORECASE)
    cleaned = re.sub(r'```', '', cleaned).strip()

    # 2. Extract substring between outermost { and }
    match = re.search(r'\{.*\}', cleaned, re.DOTALL)
    if match:
        cleaned = match.group()

    # 3. Strip trailing commas before closing brackets/braces
    cleaned = re.sub(r',\s*([}\]])', r'\1', cleaned)

    # 4. Direct parse attempt
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    # 5. Fix common newline or control character escapes
    try:
        sanitized = re.sub(r'[\x00-\x1F\x7F]', ' ', cleaned)
        return json.loads(sanitized)
    except Exception:
        pass

    return None


async def generate_study_plan(
    user_id: str,
    topic_id: str,
    target_date: str,
    hours_per_day: float = 2.0,
) -> Optional[dict]:
    """
    Analyzes document context for topic_id and generates a structured study plan up to target_date.
    """
    today = datetime.utcnow().date()
    try:
        target_dt = datetime.strptime(target_date, "%Y-%m-%d").date()
        total_days = (target_dt - today).days
        if total_days <= 0:
            total_days = 7
    except Exception:
        total_days = 7

    total_days = max(3, min(30, total_days))

    # Retrieve document text
    context_docs = []
    namespaced_topic = f"{user_id.replace('-', '_')}_{(topic_id or 'general').replace('-', '_')}"

    for tid in [namespaced_topic, topic_id, "general"]:
        try:
            collection = vector_store._collection(tid)
            if collection.count() > 0:
                data = collection.get(include=["documents"])
                documents = data.get("documents", [])
                if documents:
                    shuffled = list(documents)
                    random.shuffle(shuffled)
                    context_docs = shuffled[:15]
                    break
        except Exception:
            continue

    if not context_docs:
        docs = db.get_documents_for_user(user_id)
        for d in docs:
            fpath = d.get("file_path")
            if fpath and Path(fpath).exists():
                try:
                    chunks = process_document(fpath)
                    for c in chunks:
                        if c.get("text"):
                            context_docs.append(c["text"])
                except Exception:
                    pass

    context = "\n\n".join(context_docs)[:5000] if context_docs else "General study concepts and textbook chapters."

    prompt = STUDY_PLAN_PROMPT_TEMPLATE.format(
        target_date=target_date,
        total_days=total_days,
        hours_per_day=hours_per_day,
        context=context,
    )

    plan_data = None
    try:
        messages = [
            {"role": "system", "content": "You are a study plan generator engine that outputs ONLY structured JSON."},
            {"role": "user", "content": prompt},
        ]
        response = await ollama.chat(messages, temperature=0.5)
        plan_data = _clean_and_parse_json(response)
    except Exception as e:
        print(f"[STUDY PLAN GENERATOR] Warning: Ollama call failed: {e}")

    # Fallback structure generator if LLM returned invalid JSON
    if not plan_data:
        print("[STUDY PLAN GENERATOR] Using intelligent fallback schedule generator.")
        plan_data = {
            "title": f"Mastering {topic_id.replace('_', ' ').title()}",
            "summary": f"Comprehensive {total_days}-day study roadmap targeting completion by {target_date}.",
            "schedule": [
                {
                    "day": i + 1,
                    "topic": f"Day {i + 1}: Module & Concept Mastery",
                    "focus": "Core principles, definitions, and practice exercises",
                    "estimated_hours": hours_per_day,
                    "recommended_action": "Read chapter notes & complete self-check questions",
                    "key_concepts": ["Fundamental Principles", "Key Terms"],
                    "study_notes": f"Study notes for Day {i + 1}: Focus on understanding core definitions and applying key formulas.",
                }
                for i in range(total_days)
            ]
        }

    title = plan_data.get("title", f"Mastering {topic_id.replace('_', ' ').title()}")
    schedule = plan_data.get("schedule", [])

    if not isinstance(schedule, list) or len(schedule) == 0:
        schedule = [
            {
                "day": i + 1,
                "topic": f"Day {i + 1} Module Study",
                "focus": "Key concept review & practice questions",
                "estimated_hours": hours_per_day,
                "recommended_action": "Read document & review AI Study Notes",
                "key_concepts": ["Core Concept"],
                "study_notes": "Review key definitions and core principles in the document text.",
            }
            for i in range(total_days)
        ]

    # Ensure study_notes is present for each day
    for item in schedule:
        if not item.get("study_notes"):
            t_name = item.get("topic", "Topic")
            f_name = item.get("focus", "Focus area")
            item["study_notes"] = f"Key notes on {t_name}: Focus on understanding {f_name} and reviewing core definitions."

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


async def generate_day_study_notes(
    topic_id: str,
    day_topic: str,
    key_concepts: List[str],
    user_id: Optional[str] = None,
) -> str:
    """
    Generates rich, structured Markdown study notes for a specific day topic using Ollama & RAG.
    """
    context_docs = []
    if user_id:
        namespaced_topic = f"{user_id.replace('-', '_')}_{(topic_id or 'general').replace('-', '_')}"
        try:
            emb = await ollama.get_embedding(day_topic)
            if emb:
                search_res = vector_store.search(namespaced_topic, emb, top_k=6)
                context_docs = [c["text"] for c in search_res if c.get("text")]
        except Exception:
            pass

    if not context_docs:
        docs = db.get_documents_for_user(user_id) if user_id else []
        if not docs:
            docs = db.get_documents_for_topic(topic_id)
        for d in docs:
            fpath = d.get("file_path")
            if fpath and Path(fpath).exists():
                try:
                    chunks = process_document(fpath)
                    for c in chunks:
                        if c.get("text"):
                            context_docs.append(c["text"])
                except Exception:
                    pass

    context = "\n\n".join(context_docs)[:4000] if context_docs else "Refer to general principles for this topic."

    prompt = DAY_NOTES_PROMPT_TEMPLATE.format(
        day_topic=day_topic,
        key_concepts=", ".join(key_concepts) if key_concepts else day_topic,
        context=context,
    )

    try:
        messages = [
            {"role": "system", "content": "You are an expert tutor writing structured markdown study notes."},
            {"role": "user", "content": prompt},
        ]
        notes = await ollama.chat(messages, temperature=0.3)
        return notes.strip()
    except Exception as e:
        return f"# 📌 {day_topic} — Study Notes\n\nStudy notes generation unavailable. Please review your PDF notes for {day_topic}."
