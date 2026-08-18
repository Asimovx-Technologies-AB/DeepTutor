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

STUDY_PLAN_PROMPT_TEMPLATE = """You are an expert academic tutor and master curriculum designer.
Your goal is to build a logically structured, pedagogically sound day-by-day study roadmap based strictly on the provided document context.

Target Exam / Completion Date: {target_date}
Available Days to Study: {total_days} days
Daily Study Time: {hours_per_day} hours/day

REQUIRED PEDAGOGICAL PROGRESSION FLOW:
1. PHASE 1: Foundations & Core Terminology (Days 1 to ~25% of timeline) — Focus on definitions, prerequisites, intuition, and basic concepts.
2. PHASE 2: Core Mechanics & Deep Dive (Days ~26% to ~65% of timeline) — Focus on step-by-step algorithms, mechanisms, formulas, and working methods.
3. PHASE 3: Applied Scenarios & Synthesis (Days ~66% to ~85% of timeline) — Focus on complex problem solving, comparative trade-offs, and practical integration.
4. PHASE 4: High-Yield Exam Review & Mastery (Final ~15% of timeline) — Focus on active recall self-testing, formula cheat sheets, common exam traps, and mock practice.

Return ONLY valid JSON in this exact structure:
{{
  "title": "Short, motivating title for the study plan",
  "summary": "Brief 1-2 sentence overview of what will be mastered by {target_date}",
  "schedule": [
    {{
      "day": 1,
      "phase": "Phase 1: Foundations & Core Terminology",
      "topic": "Main Topic / Module Name for Day 1",
      "focus": "Specific concepts or sections to read & understand",
      "estimated_hours": {hours_per_day},
      "recommended_action": "Read chapter notes, review key definitions, complete basic exercises",
      "key_concepts": ["Concept 1", "Concept 2"]
    }}
  ]
}}

Rules:
- Generate a schedule spanning exactly {total_days} days (Day 1 up to Day {total_days}).
- Order the topics strictly following the 4-phase pedagogical progression flow above.
- Reserve the final day (Day {total_days}) in Phase 4 for full review, practice quiz, and self-check.
- Response MUST contain ONLY valid JSON. No conversational commentary.

DOCUMENT CONTEXT:
{context}

JSON:"""


DAY_NOTES_PROMPT_TEMPLATE = """You are an expert AI academic tutor. Generate a comprehensive, crystal-clear, highly structured study brief for a student studying the topic below from their uploaded material.
Explain the concepts in accessible language while maintaining absolute academic rigor, logical flow, and precision.

DAY TOPIC: {day_topic}
KEY CONCEPTS: {key_concepts}

DOCUMENT CONTEXT:
{context}

Format your response strictly using clean, beautiful Markdown following this logical 6-section structure:

# 📌 {day_topic} — Structured Study Notes

> **Daily Learning Goal**: [Clear, 1-sentence statement of what the student will master today]

---

## 💡 1. Conceptual Blueprint (ELI5 Intuition)
[Intuitive 2-3 sentence overview explaining what this concept is and why it matters in simple, accessible terms]

---

## 🔑 2. Core Definitions & Essential Terminology
- **[Key Term 1]**: [Clear definition and precise explanation grounded in the text]
- **[Key Term 2]**: [Clear definition and precise explanation grounded in the text]
- **[Key Term 3]**: [Clear definition and precise explanation grounded in the text]

---

## ⚙️ 3. Step-by-Step Mechanics & Workflow
1. **[Step 1 / Primary Phase]**: [Detailed explanation of how this mechanism operates]
2. **[Step 2 / Secondary Phase]**: [Detailed explanation of how this mechanism operates]
3. **[Step 3 / Output & Resolution]**: [Detailed explanation of how this mechanism operates]

---

## 📊 4. Practical Applications & Trade-Offs
- **Primary Advantages**: [Key strengths or why this method is used]
- **Limitations & Constraints**: [Trade-offs, edge cases, or complexity considerations]

---

## ⚠️ 5. Common Pitfalls & Exam Traps
> [!WARNING]
> **Exam Trap**: [Specific misunderstanding or trick question students frequently make on tests regarding {day_topic}]

---

## 🎯 6. Active Recall & Self-Check Review
1. **Q**: [High-yield practice review question testing key concepts]
   * **Answer**: [Concise, accurate answer grounded in the text]
2. **Q**: [High-yield practice review question testing key concepts]
   * **Answer**: [Concise, accurate answer grounded in the text]
"""


def _clean_and_parse_json(text: str) -> Optional[dict]:
    """Robust JSON extraction & repair helper for LLM responses."""
    if not text:
        return None

    cleaned = re.sub(r'```(?:json)?\s*', '', text, flags=re.IGNORECASE)
    cleaned = re.sub(r'```', '', cleaned).strip()

    match = re.search(r'\{.*\}', cleaned, re.DOTALL)
    if match:
        cleaned = match.group()

    cleaned = re.sub(r',\s*([}\]])', r'\1', cleaned)

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    try:
        sanitized = re.sub(r'[\x00-\x1F\x7F]', ' ', cleaned)
        return json.loads(sanitized)
    except Exception:
        pass

    return None


def _get_day_phase(day: int, total_days: int) -> str:
    pct = day / max(1, total_days)
    if pct <= 0.25:
        return "Phase 1: Foundations & Core Terminology"
    elif pct <= 0.65:
        return "Phase 2: Core Mechanics & Deep Dive"
    elif pct <= 0.85:
        return "Phase 3: Applied Scenarios & Synthesis"
    else:
        return "Phase 4: High-Yield Exam Review & Mastery"


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

    if topic_id and topic_id != "general":
        session = db.get_session(topic_id)
        if session and session.get("session_title"):
            display_topic = session["session_title"]
        else:
            display_topic = topic_id.replace("_", " ").title()

    if topic_id and topic_id != "general":
        try:
            context_docs = await get_section_context(
                user_id=user_id,
                section_id=topic_id,
                top_k=15,
            )
        except Exception:
            context_docs = []

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
                    "phase": _get_day_phase(i + 1, total_days),
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
                "phase": _get_day_phase(i + 1, total_days),
                "topic": f"Day {i + 1}: {display_topic} Study",
                "focus": "Key concept review & practice questions",
                "estimated_hours": hours_per_day,
                "recommended_action": "Read document & review AI Study Notes",
                "key_concepts": ["Core Concept"],
                "study_notes": f"Review key definitions and core principles in {display_topic}.",
            }
            for i in range(total_days)
        ]

    for item in schedule:
        if "phase" not in item or not item["phase"]:
            item["phase"] = _get_day_phase(item.get("day", 1), len(schedule))
        item["study_notes"] = ""

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
