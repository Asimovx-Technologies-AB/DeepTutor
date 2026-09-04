"""
Flashcard / Quiz Generation Engine.

Generates a structured, schema-constrained deck of question objects that can be
rendered EITHER as flip-flashcards (front = prompt, back = correct answer +
explanation) OR as a graded multiple-choice quiz — both views consume the exact
same JSON, so the frontend just toggles presentation mode.
"""

import json
import re
from typing import Any, Dict, List, Optional

from app.services.study_storage import search_fts_chunks
from app.services.study_agents import call_llm


FLASHCARD_SYSTEM_PROMPT = """You are DeepTutor's Flashcard & Quiz Engine — a specialist agent that converts \
grounded course material into a structured deck of multiple-choice question objects, dual-purposed as \
flip-flashcards and as a graded self-test.

STRICT OUTPUT CONTRACT:
Return ONLY valid JSON. No markdown fences, no prose before or after, no trailing commentary. The JSON \
MUST exactly match this structure:

{{
  "title": "<short topic heading, a few words>",
  "description": "<one line summarizing what this deck covers>",
  "initial_mode": "flashcards",
  "questions": [
    {{
      "id": "q1",
      "question_type": "multiple_choice",
      "prompt": "<the question text>",
      "options": [
        {{"id": "a", "text": "<option text>"}},
        {{"id": "b", "text": "<option text>"}},
        {{"id": "c", "text": "<option text>"}},
        {{"id": "d", "text": "<option text>"}}
      ],
      "correct_option_id": "<one of a/b/c/d>",
      "explanation": "<why the correct answer is correct, grounded in the material>",
      "hint": "<optional short nudge, omit key if not useful>",
      "correct_feedback": "<optional short verdict phrase for a correct answer>",
      "incorrect_feedback": "<optional short verdict phrase for a wrong answer>"
    }}
  ]
}}

GROUNDING RULE:
Every question and explanation must be answerable strictly from the RETRIEVED CONTEXT below. Do not invent \
facts, statistics, or claims absent from the material. If the retrieved context is too thin to support the \
requested number of distinct, non-redundant questions, generate fewer questions rather than padding with \
ungrounded or repetitive ones — a short accurate deck beats a long fabricated one.

DIFFICULTY / EXPLANATION-LEVEL CALIBRATION:
This deck must be pitched at the following explanation level: {explanation_level}
- If "eli5": use everyday words and concrete, simple scenarios in both the prompt and the options — no jargon, \
no formulas. Questions test the single core idea only, not edge cases.
- If "simple": plain language, minimal jargon, one core idea per question, straightforward distractors.
- If "advanced": assume strong prior knowledge. Test edge cases, precise definitions, derivations, and common \
misconceptions among advanced students. Use correct technical vocabulary and, where relevant, KaTeX math in \
the prompt or options ($...$ inline, $$...$$ block).
- If "standard" (default): typical course/exam-level difficulty appropriate to {subject}.

QUESTION QUALITY RULES:
1. Progression: order questions from foundational recall toward deeper application/analysis — don't front-load \
   the hardest question.
2. Exactly 4 options per question unless the material only supports a natural true/false or 2-3 option split \
   (e.g. a strict binary distinction) — in that case use 2-3 options rather than padding with a weak 4th.
3. Distractors must be plausible, not absurd — each wrong option should reflect a real misconception or a \
   commonly confused adjacent concept, not an obviously silly choice. Never make the correct answer the only \
   long option or use "all/none of the above."
4. One unambiguous correct answer per question — verify no other option could also be defended as correct.
5. No duplicate or near-duplicate questions testing the same fact twice.
6. Explanations must do real teaching: state WHY the correct answer holds and, briefly, why the most tempting \
   distractor is wrong — not just restate the correct option.
7. Mathematics/formulas: standalone block KaTeX ($$...$$) for anything requiring its own line, inline ($...$) \
   for short in-sentence terms. Never use plain-text pseudo-math ("x^2" instead of "$x^2$").
8. Tone: clear, precise, encouraging. Zero emojis. correct_feedback/incorrect_feedback (when included) should \
   be a few words, varied across questions, never mocking.
9. If the retrieved context contradicts itself across chunks, prefer the more specific/detailed chunk and note \
   the ambiguity is not something to surface to the student — just pick the best-supported answer.

Topic: {topic_title}
Subject: {subject}
Number of questions requested: {num_cards}

Retrieved Grounding Context:
{context}

Return ONLY the JSON object described above — nothing else."""


async def generate_flashcard_deck(
    session_id: str,
    topic_id: str,
    topic_title: str,
    subject: str = "General Study",
    num_cards: int = 8,
    explanation_level: str = "standard",
    initial_mode: str = "flashcards",
    override_context: Optional[str] = None
) -> Dict[str, Any]:
    """
    Generates a grounded flashcard/quiz deck for a topic with strict out-of-scope validation.
    """
    from app.services.study_storage import get_session_topics

    session_topics = get_session_topics(session_id)
    syllabus_titles = [t.get("title", "") for t in session_topics if t.get("title")]

    if override_context:
        context = override_context
    else:
        chunks = search_fts_chunks(session_id, topic_title, limit=8)
        context = "\n\n".join(
            f"--- CHUNK [{c['chunk_id']} | Page {c['page']}] ---\n{c['content']}"
            for c in chunks
        ) if chunks else ""

    # 1. Out-of-Scope / Grounding Validation Check (bypass if override_context is explicitly provided)
    if not override_context and topic_title and topic_title.lower() not in ("course material", "all topics", "general", "full material", "overview"):
        verify_prompt = f"""You are a strict syllabus relevance and academic grounding auditor.
Course Subject: {subject}
Syllabus Topics Covered in Material:
{", ".join(syllabus_titles[:15]) if syllabus_titles else "General course material"}

Requested Flashcard/Quiz Topic: "{topic_title}"

Retrieved Document Excerpt:
{context[:2500] if context else "No matching chunks found in the database."}

TASK:
Determine if "{topic_title}" is actually covered in the course syllabus or material, or if it is an out-of-scope / unrelated topic (for example: asking for "Indian forest", "culinary recipes", or "geography" for a Machine Learning course).
CRITICAL RULE: Do NOT force-match accidental keywords (for instance, do not match "Indian forest" or "tropical forestry" to "Random Forests algorithm" in Computer Science).

Return ONLY valid JSON:
{{
  "in_scope": true,
  "reason": "1 short explanation of why this topic is covered or why it is out of scope",
  "suggested_topics": ["Syllabus Topic 1", "Syllabus Topic 2", "Syllabus Topic 3"]
}}
"""
        try:
            ver_raw = await call_llm(
                verify_prompt,
                "You are an academic auditor. Output strict JSON only.",
                temperature=0.1
            )
            parsed_ver = _parse_json_relaxed(ver_raw)
            if parsed_ver and isinstance(parsed_ver, dict) and not parsed_ver.get("in_scope", True):
                return {
                    "out_of_topic": True,
                    "topic": topic_title,
                    "reason": parsed_ver.get("reason", f"The topic '{topic_title}' is not covered in your uploaded course materials for {subject}."),
                    "suggested_topics": parsed_ver.get("suggested_topics") or syllabus_titles[:5],
                    "questions": []
                }
        except Exception as e:
            print(f"[Quiz Engine Grounding Check] Note: {e}")

    # If context is empty and no syllabus match
    if not context and not syllabus_titles:
        return {
            "out_of_topic": True,
            "topic": topic_title,
            "reason": f"No indexed course material found for '{topic_title}'.",
            "suggested_topics": [],
            "questions": []
        }

    grounding_context = context or f"General topics from syllabus: {', '.join(syllabus_titles)}"

    prompt = FLASHCARD_SYSTEM_PROMPT.format(
        explanation_level=explanation_level,
        subject=subject,
        topic_title=topic_title,
        num_cards=num_cards,
        context=grounding_context[:6000],
    )

    sys_inst = "You are a precise educational content generator. Output strict JSON only. No emojis."
    raw = await call_llm(prompt, sys_inst, temperature=0.3)

    parsed = _parse_json_relaxed(raw)
    if parsed and isinstance(parsed.get("questions"), list) and parsed["questions"]:
        parsed.setdefault("title", topic_title)
        parsed.setdefault("description", f"Flashcards covering {topic_title}")
        parsed["initial_mode"] = initial_mode
        return parsed

    # Deterministic fallback if the LLM call/parse failed entirely
    return _fallback_deck(topic_title, subject, initial_mode)



def _parse_json_relaxed(raw: str) -> Optional[Dict[str, Any]]:
    """Defensive-parsing pattern: strip code fences, try direct parse,
    then regex-extract the first {...} block as a last resort."""
    if not raw:
        return None
    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*```$", "", text).strip()
    try:
        return json.loads(text, strict=False)
    except Exception:
        match = re.search(r"(\{[\s\S]*\})", text)
        if match:
            try:
                return json.loads(match.group(1), strict=False)
            except Exception:
                return None
    return None


def _fallback_deck(topic_title: str, subject: str, initial_mode: str) -> Dict[str, Any]:
    """Minimal fallback when generation fails."""
    return {
        "title": topic_title,
        "description": f"Flashcards for {topic_title}",
        "initial_mode": initial_mode,
        "questions": [
            {
                "id": "q1",
                "question_type": "multiple_choice",
                "prompt": (
                    f"What is the primary objective of studying {topic_title} in {subject}?"
                ),
                "options": [
                    {"id": "a", "text": "To understand governing mechanisms and solve quantitative exercises"},
                    {"id": "b", "text": "To memorize superficial vocabulary without principles"},
                    {"id": "c", "text": "To skip foundational derivations entirely"},
                    {"id": "d", "text": "None of the above"},
                ],
                "correct_option_id": "a",
                "explanation": (
                    f"Mastering {topic_title} requires understanding theoretical relationships, "
                    f"governing equations, and practical analytical application."
                ),
            }
        ],
    }
