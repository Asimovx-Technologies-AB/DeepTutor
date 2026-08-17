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


DAY_NOTES_PROMPT_TEMPLATE = """You are an expert AI academic tutor. Generate a comprehensive, crystal-clear, intuitive, and structured study brief for a student studying the topic below from their uploaded material.
Explain the concepts in simple, accessible language while maintaining absolute academic rigor and accuracy.

DAY TOPIC: {day_topic}
KEY CONCEPTS: {key_concepts}

DOCUMENT CONTEXT:
{context}

Format your response strictly using clean, beautiful Markdown with the following structure:

# 📌 {day_topic} — Study Notes

## 💡 Big-Picture Overview (In Simple Words)
[Clear, intuitive 2-3 sentence overview explaining what this concept is and why it matters in plain, simple terms]

## 🔑 Core Definitions & Key Terms
- **[Key Term 1]**: [Clear, intuitive definition and explanation grounded in material]
- **[Key Term 2]**: [Clear, intuitive definition and explanation grounded in material]
- **[Key Term 3]**: [Clear, intuitive definition and explanation grounded in material]

## ⚙️ How It Works (Step-by-Step)
1. **[Step 1 / Core Mechanism]**: [Clear explanation of how the process or concept works]
2. **[Step 2 / Core Mechanism]**: [Clear explanation of how the process or concept works]
3. **[Step 3 / Core Mechanism]**: [Clear explanation of how the process or concept works]

## 📝 High-Yield Exam Takeaways
- **Key Advantage / Strength**: [Why this method or concept is used]
- **Key Challenge / Limitation**: [Important trade-offs, constraints, or common exam traps]

## 🎯 Quick Self-Check Review
1. **Q**: [High-yield practice review question on this topic]
   **A**: [Concise, accurate answer]
2. **Q**: [High-yield practice review question on this topic]
   **A**: [Concise, accurate answer]
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

    # Retrieve document text strictly for this user & section
    from app.rag.section_scope import get_section_context

    context_docs: List[str] = []
    display_topic = "Study Curriculum"

    # 1. Resolve human-readable topic name
    if topic_id and topic_id != "general":
        session = db.get_session(topic_id)
        if session and session.get("session_title"):
            display_topic = session["session_title"]
        else:
            display_topic = topic_id.replace("_", " ").title()

    # 2. Retrieve document context from section or user's library
    if topic_id and topic_id != "general":
        try:
            context_docs = await get_section_context(
                user_id=user_id,
                section_id=topic_id,
                top_k=15,
            )
        except Exception:
            context_docs = []

    # 3. Fallback: Search across user's uploaded documents if topic_id had no direct vectors
    if not context_docs:
        try:
            user_docs = db.get_documents_for_user(user_id)
            for d in user_docs:
                d_tid = d.get("topic_id")
                if d_tid:
                    d_chunks = await get_section_context(user_id=user_id, section_id=d_tid, top_k=10)
                    if d_chunks:
                        context_docs.extend(d_chunks)
                        if display_topic == "Study Curriculum":
                            display_topic = d.get("file_name", "Study Plan").replace(".pdf", "")
                        break
        except Exception:
            pass

    # 4. Fallback: Extract key topics from document metadata in DB
    if not context_docs:
        docs = db.get_documents_for_user_and_topic(user_id, topic_id) or db.get_documents_for_user(user_id)
        for doc in docs:
            kts = doc.get("key_topics", [])
            if kts:
                context_docs.append(f"Document {doc.get('file_name')}: Topics include {', '.join(kts)}")
                if display_topic == "Study Curriculum":
                    display_topic = doc.get("file_name", "").replace(".pdf", "")

    context = "\n\n".join(context_docs)[:5000] if context_docs else f"Core academic curriculum and structured study topics for {display_topic}."

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
        response = await ollama.chat(messages, temperature=0.4)
        plan_data = _clean_and_parse_json(response)
    except Exception as e:
        print(f"[STUDY PLAN GENERATOR] Warning: AI chat failed: {e}")

    # Fallback structure generator if LLM returned invalid JSON
    if not plan_data:
        print("[STUDY PLAN GENERATOR] Using intelligent fallback schedule generator.")
        plan_data = {
            "title": f"Mastering {display_topic.replace('.pdf', '')}",
            "summary": f"Comprehensive {total_days}-day study roadmap targeting completion by {target_date}.",
            "schedule": [
                {
                    "day": i + 1,
                    "topic": f"Day {i + 1}: {display_topic} - Module {i + 1}",
                    "focus": "Core principles, definitions, and practice exercises",
                    "estimated_hours": hours_per_day,
                    "recommended_action": "Read chapter notes & complete self-check questions",
                    "key_concepts": ["Fundamental Principles", "Key Terms"],
                    "study_notes": f"Study notes for Day {i + 1}: Focus on understanding core definitions and applying key concepts from {display_topic}.",
                }
                for i in range(total_days)
            ]
        }

    title = plan_data.get("title", f"Mastering {display_topic.replace('.pdf', '')}")
    schedule = plan_data.get("schedule", [])

    if not isinstance(schedule, list) or len(schedule) == 0:
        schedule = [
            {
                "day": i + 1,
                "topic": f"Day {i + 1}: {display_topic} Study",
                "focus": "Key concept review & practice questions",
                "estimated_hours": hours_per_day,
                "recommended_action": "Read document & review AI Study Notes",
                "key_concepts": ["Core Concept"],
                "study_notes": f"Review key definitions and core principles in {display_topic}.",
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
    Generates rich, structured Markdown study notes for a specific day topic using AI & RAG.
    """
    from app.rag.section_scope import get_section_context

    context_docs: List[str] = []
    if user_id and topic_id and topic_id != "general":
        try:
            context_docs = await get_section_context(
                user_id=user_id,
                section_id=topic_id,
                query=day_topic,
                top_k=8,
            )
        except Exception:
            context_docs = []

    if not context_docs and user_id:
        try:
            user_docs = db.get_documents_for_user(user_id)
            for d in user_docs:
                d_tid = d.get("topic_id")
                if d_tid:
                    d_chunks = await get_section_context(user_id=user_id, section_id=d_tid, query=day_topic, top_k=6)
                    if d_chunks:
                        context_docs.extend(d_chunks)
                        break
        except Exception:
            pass

    context = "\n\n".join(context_docs)[:4000] if context_docs else f"Core academic definitions and principles of {day_topic}."

    prompt = DAY_NOTES_PROMPT_TEMPLATE.format(
        day_topic=day_topic,
        key_concepts=", ".join(key_concepts) if key_concepts else day_topic,
        context=context,
    )

    try:
        messages = [
            {"role": "system", "content": "You are an expert academic tutor writing structured markdown study notes."},
            {"role": "user", "content": prompt},
        ]
        notes = await ollama.chat(messages, temperature=0.3)
        if notes and len(notes.strip()) > 50:
            return notes.strip()
    except Exception as e:
        print(f"[STUDY PLAN] Error generating day notes: {e}")

    concepts_list = "".join([f"- **{c}**: Core theoretical foundation and practical application.\n" for c in key_concepts]) if key_concepts else f"- **{day_topic}**: Essential concepts and foundational principles.\n"
    return f"""# 📌 {day_topic} — Study Notes

## 💡 Overview & Core Objectives
Comprehensive study breakdown for **{day_topic}**. Focus on understanding core terminology and applying theoretical principles to problem solving.

## 🔑 Key Definitions & Terms
{concepts_list}
## 📝 In-Depth Breakdown
- **Core Mechanism**: Review the step-by-step concepts outlined in your textbook or lecture notes.
- **Exam Tips**: Pay close attention to standard definitions, problem formulation, and algorithmic steps.

## 🎯 Quick Self-Check Review
1. **Q**: What is the primary objective of {day_topic}?
   **A**: To solve core domain problems systematically using established principles.
2. **Q**: How do the key concepts interconnect?
   **A**: They provide the underlying mathematical and conceptual framework needed for deeper mastery.
"""
