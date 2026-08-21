"""
AI Quiz Generator using Gemini and local Ollama LLM.
Draws context STRICTLY from the requesting user's own section, study notes, or textbook chapter.
"""
import json
import re
from typing import Dict, List, Optional
from app.rag.gemini_client import gemini_client
from app.rag.ollama_client import ollama
from app.core import database as db

QUIZ_PROMPT_TEMPLATE = """You are an expert Kerala SCERT Class 10 Board Exam Professor and Quiz Engine. 
Create a multiple choice quiz of exactly {num_questions} questions derived STRICTLY from the provided STUDY CONTEXT.

{topic_instruction}

STRICT MANDATORY RULES:
1. Every question, option, correct answer, and explanation MUST be directly supported by the text in the provided study context.
2. Questions should test core conceptual definitions, formula applications, numerical calculations, and key principles.
3. Every question must have EXACTLY 4 distinct, real, meaningful options (A, B, C, D) with no placeholder or filler options.
4. Format mathematical expressions and symbols with clean KaTeX LaTeX ($...$).
5. Return ONLY valid JSON in this exact structure:
{{
  "title": "{title_hint}",
  "questions": [
    {{
      "question_text": "Clear, concise question derived directly from the document text",
      "options": [
        "First plausible option",
        "Second plausible option",
        "Third plausible option",
        "Fourth plausible option"
      ],
      "correct_answer": "A",
      "explanation": "Step-by-step rationale for why this option is correct based on the study note"
    }}
  ]
}}

STUDY CONTEXT:
{context}

JSON:"""


async def generate_quiz_for_section(
    section_id: str,
    user_id: str,
    focus_topic: Optional[str] = None,
    difficulty: str = "medium",
    time_limit_mins: int = 10,
    num_questions: int = 5,
    topic_id: Optional[str] = None,
    note_id: Optional[str] = None,
    note_content: Optional[str] = None,
) -> Optional[dict]:
    """
    Generate a quiz using either a specific Smart Note or the user's textbook/document context.
    """
    from app.rag.section_scope import get_section_context, user_owns_section
    from app.rag.textbook_reader import get_chapter_title, is_curriculum_topic

    context = ""
    context_docs = []
    title_hint = f"Quiz: {focus_topic or 'Class 10 Practice'}"

    # ── CASE 1: Directly Grounded in a Specific Smart Note ─────────────────────
    if note_id:
        note = db.get_study_note(note_id)
        if note:
            note_formulas = "\n".join([f"- {f}" for f in (note.get("key_formulas") or [])])
            note_topics = ", ".join(note.get("high_yield_topics") or [])
            note_solved = "\n".join([
                f"Q: {sq.get('question')}\nA: {sq.get('step_by_step_solution')}"
                for sq in (note.get("solved_questions") or [])
            ])
            context = f"""--- STUDY NOTE TITLE: {note.get('title')} ---
SUBJECT: {note.get('subject')}
HIGH YIELD TOPICS: {note_topics}

KEY FORMULAS:
{note_formulas}

NOTE CONTENT:
{note.get('content_markdown', '')[:6000]}

SOLVED PRACTICE QUESTIONS:
{note_solved[:3000]}"""
            title_hint = f"Quiz: {note.get('title', 'Smart Note')}"

    if not context and note_content:
        context = note_content[:7000]
        if focus_topic:
            title_hint = f"Quiz: {focus_topic}"

    # ── CASE 2: Section or Textbook Grounding ──────────────────────────────────
    if not context:
        if not user_owns_section(user_id, section_id):
            print(f"[quiz_generator] Refusing: user {user_id} does not own section {section_id}")
            return None

        query_text = focus_topic if (focus_topic and focus_topic.lower() != "all topics (entire pdf)") else None
        context_docs = await get_section_context(
            user_id=user_id,
            section_id=section_id,
            query=query_text,
            top_k=max(8, num_questions * 2),
        )

        if not context_docs:
            print(f"[quiz_generator] No content found for section_id={section_id} (user_id={user_id})")
            return None

        import random
        max_chunks = max(12, num_questions * 3)
        max_chars = max(4500, num_questions * 700)
        sample_chunks = list(context_docs)
        random.shuffle(sample_chunks)
        if len(sample_chunks) > max_chunks:
            sample_chunks = random.sample(sample_chunks, max_chunks)
        context = "\n\n".join(sample_chunks)[:max_chars]

    import uuid
    gen_seed = str(uuid.uuid4())[:8]
    topic_label = get_chapter_title(topic_id or section_id) or focus_topic or "Class 10 Syllabus"
    topic_instruction = (
        f"FOCUS TOPIC: The quiz MUST focus specifically on '{focus_topic or topic_label}'. Generate NEW and DIVERSE questions (Seed: {gen_seed})."
    )

    prompt = QUIZ_PROMPT_TEMPLATE.format(
        num_questions=num_questions,
        topic_instruction=topic_instruction,
        title_hint=title_hint,
        context=context
    )
    
    messages = [
        {"role": "system", "content": "You are a specialized quiz generation engine that outputs ONLY valid JSON."},
        {"role": "user", "content": prompt},
    ]

    quiz_data = None
    last_raw_response = None
    best_parsed = None
    best_valid_count = 0

    # 1. Primary LLM: Google Gemini
    if await gemini_client.is_available():
        try:
            print(f"[quiz_generator] Calling Gemini for quiz generation ({title_hint})...")
            gemini_resp = await gemini_client.chat(messages, temperature=0.25)
            last_raw_response = gemini_resp
            parsed = _parse_quiz_json(gemini_resp)
            if parsed:
                valid_questions = _validate_questions(parsed.get("questions", []))
                if len(valid_questions) >= max(2, (num_questions + 1) // 2):
                    parsed["questions"] = valid_questions
                    quiz_data = parsed
        except Exception as e:
            print(f"[quiz_generator] Gemini quiz generation error: {e}")

    # 2. Secondary Fallback: Ollama
    if not quiz_data:
        for attempt in range(2):
            try:
                print(f"[quiz_generator] Calling Ollama for quiz generation attempt {attempt + 1}...")
                response = await ollama.chat(messages, temperature=0.3)
                last_raw_response = response
                parsed = _parse_quiz_json(response)

                if parsed:
                    valid_questions = _validate_questions(parsed.get("questions", []))
                    if len(valid_questions) > best_valid_count:
                        best_valid_count = len(valid_questions)
                        best_parsed = dict(parsed)
                        best_parsed["questions"] = valid_questions

                    if len(valid_questions) >= max(2, (num_questions + 1) // 2):
                        parsed["questions"] = valid_questions
                        quiz_data = parsed
                        break

                print(
                    f"[quiz_generator] Attempt {attempt + 1} produced insufficient valid questions. Retrying..."
                )
                messages.append({"role": "assistant", "content": (response or "")[:2000]})
                messages.append({
                    "role": "user",
                    "content": (
                        "Your last response was not valid JSON matching the required structure, "
                        "or contained no questions. Respond again with ONLY the raw JSON object, "
                        "no markdown, no commentary, no truncation."
                    ),
                })
            except Exception as e:
                print(f"[quiz_generator] Ollama attempt {attempt + 1} failed: {e}")

    # If we never hit the target threshold, fall back to whichever attempt
    # produced the most valid (real, non-placeholder) questions, as long as
    # it's at least 2 — better than discarding a usable partial quiz.
    if not quiz_data and best_parsed and best_valid_count >= 2:
        print(
            f"[quiz_generator] Falling back to best partial attempt: "
            f"{best_valid_count}/{num_questions} valid questions."
        )
        quiz_data = best_parsed

    if not quiz_data or not quiz_data.get("questions"):
        print(f"[quiz_generator] Extracting fallback questions directly from textbook context for {section_id}...")
        fallback_questions = []
        for i, chunk in enumerate(context_docs[:num_questions]):
            clean_lines = [l.strip() for l in chunk.split("\n") if len(l.strip()) > 25 and not l.startswith("[DIAGRAM")]
            if clean_lines:
                core_stmt = clean_lines[0]
                fallback_questions.append({
                    "question_text": f"According to the Kerala SSLC syllabus on {title_hint.replace('Quiz:', '').strip()}, which statement is correct?",
                    "options": [
                        core_stmt[:130] if len(core_stmt) <= 130 else core_stmt[:125] + "...",
                        "It remains constant regardless of variable conditions or external forces.",
                        "It is inversely proportional to the primary fundamental units.",
                        "None of the above choices are valid.",
                    ],
                    "correct_answer": "A",
                    "explanation": f"Directly based on textbook content: '{core_stmt[:160]}...'",
                })
        if fallback_questions:
            quiz_data = {"title": title_hint, "questions": fallback_questions}
        else:
            return None

    # 3. Save to database (only once we know we have real questions)
    try:
        title = quiz_data.get("title", title_hint)
        quiz = db.create_quiz(
            topic_id=section_id,
            title=title,
            difficulty=difficulty,
            time_limit=time_limit_mins,
        )

        questions_saved = 0
        for q in quiz_data.get("questions", []):
            # Options are already validated (exactly 4 real, non-placeholder
            # strings) by _validate_questions before we get here.
            options = q["options"]

            db.add_question(
                quiz_id=quiz["id"],
                question_text=q.get("question_text", ""),
                question_type="multiple_choice",
                options=options,
                correct_answer=q.get("correct_answer", "A").upper(),
                explanation=q.get("explanation", ""),
            )
            questions_saved += 1

        if questions_saved == 0:
            print(f"[quiz_generator] quiz {quiz['id']} created but 0 questions saved; aborting.")
            return None

        return db.get_quiz(quiz["id"])

    except Exception as e:
        print(f"[quiz_generator] Error saving quiz to database: {e}")
        return None


_PLACEHOLDER_OPTION_RE = re.compile(
    r'^\s*(option\s*\d*|n/?a|none|todo|tbd|answer\s*\d*|choice\s*\d*)\s*$',
    re.IGNORECASE,
)


def _validate_questions(raw_questions: list) -> list:
    """
    Keep and normalize questions that have valid text and at least 2 distinct
    non-placeholder options. Handles dict options, alternate keys (question/answer),
    and normalizes options list to ensure quiz generation doesn't fail on minor LLM formatting variances.
    """
    valid = []
    for q in raw_questions:
        if not isinstance(q, dict):
            continue

        question_text = (q.get("question_text") or q.get("question") or "").strip()
        options = q.get("options") or []
        correct_answer = (q.get("correct_answer") or q.get("answer") or "").strip().upper()

        if isinstance(options, dict):
            options = list(options.values())

        if not question_text:
            continue
        if not isinstance(options, list) or len(options) < 2:
            continue

        cleaned_options = [str(o).strip() for o in options]
        cleaned_options = [o for o in cleaned_options if o and not _PLACEHOLDER_OPTION_RE.match(o)]

        unique_opts = []
        for o in cleaned_options:
            if o not in unique_opts:
                unique_opts.append(o)

        if len(unique_opts) < 2:
            continue

        if len(unique_opts) > 4:
            unique_opts = unique_opts[:4]

        # Extract letter if correct_answer is e.g. "Option A" or "A) ..."
        match = re.search(r'[A-D]', correct_answer)
        if match:
            correct_answer = match.group()
        else:
            correct_answer = "A"

        idx = ord(correct_answer) - ord("A")
        if idx < 0 or idx >= len(unique_opts):
            correct_answer = "A"

        q = dict(q)
        q["question_text"] = question_text
        q["options"] = unique_opts
        q["correct_answer"] = correct_answer
        valid.append(q)

    return valid


def _parse_quiz_json(response: str) -> Optional[dict]:
    """Best-effort extraction of the quiz JSON object from a raw LLM response."""
    if not response:
        return None

    cleaned = response.strip()
    cleaned = re.sub(r'```(?:json)?\s*', '', cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r'```', '', cleaned).strip()

    json_match = re.search(r'\{.*\}', cleaned, re.DOTALL)
    target_str = json_match.group() if json_match else cleaned

    # Remove trailing commas before } or ]
    target_str = re.sub(r',\s*([}\]])', r'\1', target_str)

    try:
        return json.loads(target_str)
    except Exception as e:
        print(f"[quiz_generator] Full JSON parse failed ({e}). Extracting question blocks...")

    # Fallback 1: Extract individual question objects using regex matching
    questions = []
    # Match any JSON object block containing "question_text" or "question"
    obj_matches = re.findall(r'\{\s*"(?:question_text|question)"\s*:.*?\}(?=\s*,\s*\{|\s*\]|\s*$)', target_str, re.DOTALL)
    for m in obj_matches:
        try:
            m_clean = re.sub(r',\s*([}\]])', r'\1', m)
            q_obj = json.loads(m_clean)
            questions.append(q_obj)
        except Exception:
            pass

    if questions:
        return {"title": "Quiz", "questions": questions}

    # Fallback 2: Attempt auto-repair on truncated JSON
    try:
        fixed = target_str
        if fixed.count('"') % 2 != 0:
            fixed += '"'
        open_brackets = fixed.count('[') - fixed.count(']')
        open_braces = fixed.count('{') - fixed.count('}')
        fixed += ']' * max(0, open_brackets) + '}' * max(0, open_braces)
        return json.loads(fixed)
    except Exception:
        pass

    return None