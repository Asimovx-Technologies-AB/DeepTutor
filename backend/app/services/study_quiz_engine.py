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
  "title": "<short topic heading, 2-5 words>",
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

MANDATORY CARD COUNT RULE:
You MUST generate EXACTLY {num_cards} distinct flashcard questions (or at minimum 6 to 8 questions).
DO NOT generate only 1 or 2 meta-questions about the overall topic title.
You MUST break down the provided material into separate, atomic questions covering distinct subtopics, definitions, classifications, formulas, facts, and key concepts.

GROUNDING RULE:
Every question and explanation must be answerable strictly from the RETRIEVED CONTEXT below. Do not invent \
facts, statistics, or claims absent from the material.

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
2. Exactly 4 options per question unless the material only supports a natural true/false or 2-3 option split.
3. Distractors must be plausible, not absurd — each wrong option should reflect a real misconception or a \
   commonly confused adjacent concept, not an obviously silly choice. Never make the correct answer the only \
   long option or use "all/none of the above."
4. One unambiguous correct answer per question — verify no other option could also be defended as correct.
5. No duplicate or near-duplicate questions testing the same fact twice.
6. Explanations must do real teaching: state WHY the correct answer holds and, briefly, why the most tempting \
   distractor is wrong.
7. Mathematics and Technical Formulas: Format all mathematical and technical expressions in clean, valid KaTeX syntax. \
For in-sentence or inline equations, ALWAYS use single dollar signs `$equation$` (for example `$d_k$`, `$\\text{{Attention}}(Q, K, V) = \\text{{softmax}}\\left(\\frac{{QK^T}}{{\\sqrt{{d_k}}}}\\right)V$`). \
NEVER use double dollar signs `$$` inside the middle of a sentence or inside options. Use double dollar signs `$$...$$` ONLY for standalone display block equations on their own separate line.
8. Noisy Text Removal & Clear Tone: Keep prompts, options, and explanations direct, clear, and focused. Avoid noisy meta-commentary (e.g., 'According to the text...', 'As mentioned above...'). Zero emojis.

Topic: {topic_title}
Subject: {subject}
Number of questions requested: {num_cards}

Retrieved Grounding Context:
{context}

Return ONLY the JSON object described above — nothing else."""


def sanitize_topic_title(raw_title: str) -> str:
    """Sanitizes topic titles by cleaning markdown formatting and stripping redundant master/guide suffixes."""
    if not raw_title:
        return "Course Material"
    clean = re.sub(r"[\*#_`~]", "", raw_title).strip()
    clean = re.sub(
        r"\s*[\–\—\-:]\s*(Exhaustive\s+)?(Master\s+)?(Explanation|Guide|Summary|Notes|Overview|Lesson|Lecture|Chapter|Study Deck).*",
        "",
        clean,
        flags=re.IGNORECASE
    ).strip()
    clean = re.sub(r"\s+in\s+Class-?\d+.*$", "", clean, flags=re.IGNORECASE).strip()
    return clean or "Course Material"


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

    clean_topic = sanitize_topic_title(topic_title)
    
    # Meta-referential query safety fallback when no override_context is supplied
    from app.services.study_agents import is_meta_referential_query
    if is_meta_referential_query(clean_topic) and not override_context:
        clean_topic = sanitize_topic_title(subject)

    if override_context:
        context = override_context
    else:
        chunks = search_fts_chunks(session_id, clean_topic, limit=8)
        context = "\n\n".join(
            f"--- CHUNK [{c['chunk_id']} | Page {c['page']}] ---\n{c['content']}"
            for c in chunks
        ) if chunks else ""

    # 1. Out-of-Scope / Grounding Validation Check (bypass if override_context is explicitly provided)
    if not override_context and clean_topic and clean_topic.lower() not in ("course material", "all topics", "general", "full material", "overview"):
        verify_prompt = f"""You are a strict syllabus relevance and academic grounding auditor.
Course Subject: {subject}
Syllabus Topics Covered in Material:
{", ".join(syllabus_titles[:15]) if syllabus_titles else "General course material"}

Requested Flashcard/Quiz Topic: "{clean_topic}"

Retrieved Document Excerpt:
{context[:2500] if context else "No matching chunks found in the database."}

TASK:
Determine if "{clean_topic}" is actually covered in the course syllabus or material, or if it is an out-of-scope / unrelated topic.
CRITICAL RULE: Do NOT force-match accidental keywords.

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
                    "topic": clean_topic,
                    "reason": parsed_ver.get("reason", f"The topic '{clean_topic}' is not covered in your uploaded course materials for {subject}."),
                    "suggested_topics": parsed_ver.get("suggested_topics") or syllabus_titles[:5],
                    "questions": []
                }
        except Exception as e:
            print(f"[Quiz Engine Grounding Check] Note: {e}")

    # If context is empty and no syllabus match
    if not context and not syllabus_titles:
        return {
            "out_of_topic": True,
            "topic": clean_topic,
            "reason": f"No indexed course material found for '{clean_topic}'.",
            "suggested_topics": [],
            "questions": []
        }

    grounding_context = context or f"General topics from syllabus: {', '.join(syllabus_titles)}"

    prompt = FLASHCARD_SYSTEM_PROMPT.format(
        explanation_level=explanation_level,
        subject=subject,
        topic_title=clean_topic,
        num_cards=num_cards,
        context=grounding_context[:6000],
    )

    sys_inst = "You are a precise educational content generator. Output strict JSON only. No emojis."
    raw = await call_llm(prompt, sys_inst, temperature=0.3)

    parsed = _parse_json_relaxed(raw)
    questions = []
    if parsed and isinstance(parsed.get("questions"), list):
        questions = parsed["questions"]

    if len(questions) < 3:
        extracted = _extract_question_objects(raw)
        if len(extracted) > len(questions):
            questions = extracted

    # If we got at least 3 valid questions from the LLM, top up to 6+ if needed and return
    if len(questions) >= 3:
        if len(questions) < 6:
            fb = _fallback_deck(clean_topic, subject, initial_mode)
            existing_prompts = {q.get("prompt", "") for q in questions}
            for extra in fb["questions"]:
                if len(questions) >= 6:
                    break
                if extra["prompt"] not in existing_prompts:
                    extra["id"] = f"q{len(questions)+1}"
                    questions.append(extra)

        title = parsed.get("title") if parsed else None
        title = sanitize_topic_title(title or clean_topic)
        desc = parsed.get("description") if parsed else None
        deck = {
            "title": title,
            "description": desc or f"Flashcards covering {title}",
            "initial_mode": initial_mode,
            "questions": questions
        }
        return _sanitize_deck_content(deck)

    # Deterministic multi-card fallback if the LLM call/parse failed entirely
    return _sanitize_deck_content(_fallback_deck(clean_topic, subject, initial_mode))


def _clean_math_and_noise(text: str) -> str:
    """Normalizes inline KaTeX delimiters and removes noisy meta-commentary."""
    if not text or not isinstance(text, str):
        return text or ""
    # Convert inline $$...$$ inside a sentence to $...$
    cleaned = re.sub(r"\$\$([^$\n]+?)\$\$", r"$\1$", text)
    # Strip unnecessary noisy intros like "According to the passage, " or "Based on the provided text, "
    cleaned = re.sub(
        r"^(According to (the )?(text|passage|module|notes|material),?\s*|Based on (the )?(text|passage|module|notes|material),?\s*)",
        "",
        cleaned,
        flags=re.IGNORECASE
    )
    return cleaned.strip()


def _sanitize_deck_content(deck: Dict[str, Any]) -> Dict[str, Any]:
    """Applies math KaTeX normalization and noise removal across all questions, options, and explanations."""
    if not deck or not isinstance(deck, dict):
        return deck
    
    questions = deck.get("questions") or []
    sanitized_questions = []
    for q in questions:
        if not isinstance(q, dict):
            continue
        prompt = _clean_math_and_noise(q.get("prompt", ""))
        explanation = _clean_math_and_noise(q.get("explanation", ""))
        hint = _clean_math_and_noise(q.get("hint", "")) if q.get("hint") else None
        correct_fb = _clean_math_and_noise(q.get("correct_feedback", "")) if q.get("correct_feedback") else None
        incorrect_fb = _clean_math_and_noise(q.get("incorrect_feedback", "")) if q.get("incorrect_feedback") else None
        
        options = []
        for opt in q.get("options", []):
            if isinstance(opt, dict):
                options.append({
                    "id": str(opt.get("id", "")).strip().lower(),
                    "text": _clean_math_and_noise(opt.get("text", ""))
                })
        
        sanitized_q = dict(q)
        sanitized_q["prompt"] = prompt
        sanitized_q["explanation"] = explanation
        sanitized_q["options"] = options
        if hint is not None:
            sanitized_q["hint"] = hint
        if correct_fb is not None:
            sanitized_q["correct_feedback"] = correct_fb
        if incorrect_fb is not None:
            sanitized_q["incorrect_feedback"] = incorrect_fb
            
        sanitized_questions.append(sanitized_q)
        
    deck["questions"] = sanitized_questions
    return deck


def _parse_json_relaxed(raw: str) -> Optional[Dict[str, Any]]:
    """Defensive-parsing pattern: strip code fences, clean trailing commas, try direct parse,
    then regex-extract the first {...} block as a last resort."""
    if not raw:
        return None
    text = raw.strip()
    if "```" in text:
        match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text, flags=re.IGNORECASE)
        if match:
            text = match.group(1).strip()
        else:
            text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
            text = re.sub(r"\s*```$", "", text).strip()
    
    cleaned = re.sub(r",\s*([\]\}])", r"\1", text)
    try:
        return json.loads(cleaned, strict=False)
    except Exception:
        pass

    try:
        return json.loads(text, strict=False)
    except Exception:
        match = re.search(r"(\{[\s\S]*\})", text)
        if match:
            try:
                sub_text = re.sub(r",\s*([\]\}])", r"\1", match.group(1))
                return json.loads(sub_text, strict=False)
            except Exception:
                pass
    return None


def _extract_question_objects(raw_text: str) -> List[Dict[str, Any]]:
    """Regex-extract individual question objects from raw LLM output if top-level JSON parse was partial."""
    questions = []
    if not raw_text:
        return questions
    matches = re.findall(r'\{\s*"id"\s*:\s*"q\d+"[\s\S]*?"explanation"\s*:\s*".*?"\s*\}', raw_text, re.DOTALL)
    for m in matches:
        m_cleaned = re.sub(r",\s*([\]\}])", r"\1", m)
        try:
            q = json.loads(m_cleaned, strict=False)
            if isinstance(q, dict) and "prompt" in q and "options" in q:
                questions.append(q)
        except Exception:
            continue
    return questions


def _fallback_deck(topic_title: str, subject: str, initial_mode: str) -> Dict[str, Any]:
    """Robust 6-card fallback deck when LLM generation or parsing fails."""
    title = sanitize_topic_title(topic_title)
    return {
        "title": title,
        "description": f"Interactive study deck covering {title}",
        "initial_mode": initial_mode,
        "questions": [
            {
                "id": "q1",
                "question_type": "multiple_choice",
                "prompt": f"What is the foundational concept behind {title}?",
                "options": [
                    {"id": "a", "text": "Understanding core principles, mechanisms, and governing theoretical frameworks"},
                    {"id": "b", "text": "Memorizing arbitrary definitions without underlying context"},
                    {"id": "c", "text": "Ignoring key structural elements and empirical observations"},
                    {"id": "d", "text": "Applying unrelated methodologies from outside the domain"}
                ],
                "correct_option_id": "a",
                "explanation": f"Mastering {title} requires understanding its core governing framework and foundational mechanics rather than superficial recall."
            },
            {
                "id": "q2",
                "question_type": "multiple_choice",
                "prompt": f"Which of the following best characterizes the primary classification in {title}?",
                "options": [
                    {"id": "a", "text": "Systematic categorization based on specific functional and structural attributes"},
                    {"id": "b", "text": "Random grouping without defined analytical criteria"},
                    {"id": "c", "text": "Single immutable category with no sub-classifications"},
                    {"id": "d", "text": "Solely subjective evaluation with no standardized parameters"}
                ],
                "correct_option_id": "a",
                "explanation": f"In {title}, classification relies on clear, objective criteria that group components by structural or operational traits."
            },
            {
                "id": "q3",
                "question_type": "multiple_choice",
                "prompt": f"Why is {title} critical to study within {subject}?",
                "options": [
                    {"id": "a", "text": "It provides necessary analytical tools for problem solving and real-world application"},
                    {"id": "b", "text": "It is an isolated topic with no practical relevance"},
                    {"id": "c", "text": "It completely contradicts standard laws of {subject}"},
                    {"id": "d", "text": "It replaces all prior subject foundations"}
                ],
                "correct_option_id": "a",
                "explanation": f"{title} acts as a vital bridge in {subject}, providing methods to analyze complex problems."
            },
            {
                "id": "q4",
                "question_type": "multiple_choice",
                "prompt": f"What is a common misconception when studying {title}?",
                "options": [
                    {"id": "a", "text": "Assuming superficial indicators fully explain complex underlying dynamics"},
                    {"id": "b", "text": "Verifying empirical evidence before drawing conclusions"},
                    {"id": "c", "text": "Differentiating between causes and effects"},
                    {"id": "d", "text": "Using standardized formulas correctly"}
                ],
                "correct_option_id": "a",
                "explanation": f"Students often confuse surface-level observations with deeper underlying causes in {title}."
            },
            {
                "id": "q5",
                "question_type": "multiple_choice",
                "prompt": f"How should one evaluate key scenarios related to {title}?",
                "options": [
                    {"id": "a", "text": "By analyzing key variables, governing constraints, and contextual conditions"},
                    {"id": "b", "text": "By guessing without examining provided data"},
                    {"id": "c", "text": "By discarding boundary conditions and constraints"},
                    {"id": "d", "text": "By relying exclusively on single-sample anecdotes"}
                ],
                "correct_option_id": "a",
                "explanation": f"Proper evaluation requires examining constraints, inputs, and systemic relationships in {title}."
            },
            {
                "id": "q6",
                "question_type": "multiple_choice",
                "prompt": f"What is the ultimate takeaway when mastering {title} in {subject}?",
                "options": [
                    {"id": "a", "text": "Synthesizing core rules, analytical models, and practical applications"},
                    {"id": "b", "text": "Abandoning critical analysis in favor of rote repetition"},
                    {"id": "c", "text": "Limiting study to introductory definitions only"},
                    {"id": "d", "text": "Ignoring real-world case studies"}
                ],
                "correct_option_id": "a",
                "explanation": f"Mastery of {title} is achieved when theoretical knowledge can be synthesized to solve practical problems in {subject}."
            }
        ]
    }

