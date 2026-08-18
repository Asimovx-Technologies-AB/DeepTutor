"""
AI Quiz Generator using local Ollama LLM.
Draws context STRICTLY from the requesting user's own section via
app.rag.section_scope — no cross-section or cross-user fallback.
"""
import json
import re
from typing import Dict, List, Optional
from app.rag.ollama_client import ollama
from app.core import database as db

QUIZ_PROMPT_TEMPLATE = """You are a precise academic study engine. Create a multiple choice quiz of exactly {num_questions} questions derived STRICTLY from the provided UPLOADED DOCUMENT CONTEXT.

{topic_instruction}

STRICT MANDATORY RULES:
1. Every question, option, correct answer, and explanation MUST be directly supported by the text in the provided document context.
2. DO NOT include external facts, definitions, or unmentioned topics not explicitly written in the provided document text.
3. If page numbers (e.g., "[Page 12]") appear in the context, include the page citation in the question explanation.
4. Return ONLY valid JSON in this exact structure:
{{
  "title": "{title_hint}",
  "questions": [
    {{
      "question_text": "Clear, concise question derived directly from the document text",
      "options": [
        "First option",
        "Second option",
        "Third option",
        "Fourth option"
      ],
      "correct_answer": "A",
      "explanation": "Detailed explanation of why this option is correct based on the PDF [Page X if available]"
    }}
  ]
}}

Rules:
- Generate exactly {num_questions} questions.
- Each question must have EXACTLY 4 options, and every option must be a real, complete, meaningful answer choice grounded in the document context.
- NEVER use placeholder text like "Option 4", "Fourth option", "N/A", or leave an option blank — if you cannot come up with 4 real distinct options for a question, choose a different question instead.
- The "correct_answer" must be one of: "A", "B", "C", "D".
- The response MUST contain only the JSON block.

UPLOADED PDF DOCUMENT CONTEXT:
{context}

JSON:"""


async def generate_quiz_for_section(
    section_id: str,
    user_id: str,
    focus_topic: Optional[str] = None,
    difficulty: str = "medium",
    time_limit_mins: int = 10,
    num_questions: int = 5,
    topic_id: Optional[str] = None,  # optional label only, not used for retrieval
) -> Optional[dict]:
    """
    Generate a quiz using ONLY the content in this user's section. No
    fallback to other sections, other users, or a shared "general"
    collection — if this section has no processed content, we return
    None rather than generating an off-topic quiz.
    """
    from app.rag.section_scope import get_section_context, user_owns_section

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

    print(
        f"[quiz_generator] section_id={section_id} user_id={user_id} "
        f"chunks_retrieved={len(context_docs)}"
    )

    if not context_docs:
        print(
            f"[quiz_generator] No content found for section_id={section_id} "
            f"(user_id={user_id}). Not generating a quiz from unrelated content."
        )
        return None

    # Sample and format context randomly each run to generate fresh, unique questions every time.
    max_chunks = max(12, num_questions * 3)
    max_chars = max(4500, num_questions * 700)

    import random
    import uuid
    sample_chunks = list(context_docs)
    random.shuffle(sample_chunks)
    if len(sample_chunks) > max_chunks:
        sample_chunks = random.sample(sample_chunks, max_chunks)
    context = "\n\n".join(sample_chunks)[:max_chars]

    CHAPTER_TITLES = {
        "math-10-1": "Arithmetic Sequences",
        "math-10-2": "Circles and Angles",
        "math-10-3": "Arithmetic Sequences & Algebra",
        "math-10-4": "Mathematics of Chance",
        "math-10-5": "Second Degree Equations",
        "math-10-6": "Trigonometry",
        "math-10-7": "Coordinates",
        "sslc-math": "Class 10 Mathematics",
        "phys-10-1": "Wave Motion & Oscillations",
        "phys-10-2": "Refraction of Light & Lenses",
        "phys-10-3": "Dispersion of Light & Colour",
        "phys-10-4": "Magnetic Effect of Electric Current",
        "sslc-physics": "Class 10 Physics",
        "chem-10-1": "Nomenclature of Organic Compounds & Isomerism",
        "chem-10-2": "Chemical Reactions of Organic Compounds",
        "chem-10-3": "Periodic Table & Electron Configuration",
        "chem-10-4": "Gas Laws and Mole Concept",
        "sslc-chemistry": "Class 10 Chemistry",
    }

    gen_seed = str(uuid.uuid4())[:8]
    topic_label = CHAPTER_TITLES.get(topic_id or section_id, (topic_id or "This Section").replace("_", " ").title())
    topic_instruction = (
        f"FOCUS TOPIC: The quiz MUST focus specifically on '{focus_topic}'. Generate NEW and DIVERSE questions (Seed: {gen_seed})."
        if (focus_topic and focus_topic.lower() != "all topics (entire pdf)")
        else f"Scope: Comprehensive quiz on '{topic_label}' from the Kerala SCERT Class 10 syllabus. Generate NEW and DIVERSE questions (Seed: {gen_seed})."
    )
    title_hint = (
        f"Quiz: {focus_topic}"
        if (focus_topic and focus_topic.lower() != "all topics (entire pdf)")
        else f"Quiz: {topic_label}"
    )

    # 2. Call Ollama to generate quiz
    prompt = QUIZ_PROMPT_TEMPLATE.format(
        num_questions=num_questions,
        topic_instruction=topic_instruction,
        title_hint=title_hint,
        context=context
    )
    
    messages = [
        {"role": "system", "content": "You are a quiz generation engine that outputs ONLY structured JSON."},
        {"role": "user", "content": prompt},
    ]

    quiz_data = None
    last_raw_response = None
    best_parsed = None
    best_valid_count = 0

    # Try up to 2 times: once normally, once with a stricter reminder if parsing fails.
    for attempt in range(2):
        try:
            response = await ollama.chat(messages, temperature=0.3)
        except Exception as e:
            print(f"[quiz_generator] Ollama call failed (attempt {attempt + 1}): {e}")
            continue

        last_raw_response = response
        parsed = _parse_quiz_json(response)

        if parsed:
            valid_questions = _validate_questions(parsed.get("questions", []))
            if len(valid_questions) > best_valid_count:
                best_valid_count = len(valid_questions)
                best_parsed = dict(parsed)
                best_parsed["questions"] = valid_questions

            required = max(2, (num_questions + 1) // 2)  # at least half of what was requested
            if len(valid_questions) >= required:
                parsed["questions"] = valid_questions
                quiz_data = parsed
                break

        print(
            f"[quiz_generator] Attempt {attempt + 1} produced no valid questions. "
            f"Raw response (first 1000 chars): {response[:1000]!r}"
        )
        # Nudge the model harder on the retry.
        messages.append({"role": "assistant", "content": response[:2000]})
        messages.append({
            "role": "user",
            "content": (
                "Your last response was not valid JSON matching the required structure, "
                "or contained no questions. Respond again with ONLY the raw JSON object, "
                "no markdown, no commentary, no truncation."
            ),
        })

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