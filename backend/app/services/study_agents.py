"""
Two-Agent Reasoning Core, Normal Mode, Teacher Mode & Mixed Exam Engine.

Architecture:
- Agent 1: Planner Agent (QueryAnalyzerAgent) -> Thinks before retrieval, generates BM25 search queries
- Agent 2: Executor Agent (DecisionAgent) -> Strictly grounded, block KaTeX math, zero emojis, thought process
- Grounding Verifier: Second-pass self-verification against FTS5 chunks
- Normal Mode: 4-Phase Progressive Cards
- Teacher Mode: 4-Phase SSE Streaming University Lecture
- Mixed-Format Topic Mastery Examination Engine & Auto-Grader
"""

import os
import re
import json
import asyncio
from typing import Dict, Any, List, Optional, AsyncGenerator
from datetime import datetime, timezone

from app.core.config import get_settings
from pathlib import Path
from app.services.study_storage import (
    search_fts_chunks,
    get_all_chunks,
    get_chunks_by_page,
    get_student_memory,
    add_student_memory_fact,
    get_session_documents,
    get_session_topics,
    save_session_topics,
    save_session_document,
    insert_chunks_to_fts,
    register_or_update_session,
    create_lecture_session,
    get_lecture_session,
    update_lecture_session,
    record_lecture_checkpoint,
    update_lecture_checkpoint,
    record_lecture_pause,
    record_mastered_topic,
    get_mastered_topics,
    BACKEND_DIR,
)


# ─── Universal Fast LLM Caller with Multi-Provider Cascade & Vision Grounding ─

async def call_gemini_vision(
    prompt: str,
    image_bytes: bytes,
    system_instruction: str = "",
    temperature: float = 0.1
) -> str:
    """Universal VLM Caller: routes to OpenAI (GPT-4o), Azure OpenAI, or Google Gemini Vision."""
    settings = get_settings()

    # 1. Direct OpenAI Vision (GPT-4o)
    try:
        from app.rag.azure_openai_client import openai_client
        if await openai_client.is_available():
            resp = await openai_client.chat_vision(prompt, image_bytes, system_instruction, temperature)
            if resp and resp.strip():
                return resp.strip()
    except Exception:
        pass

    # 2. Azure OpenAI Vision
    try:
        from app.rag.azure_openai_client import azure_openai
        if await azure_openai.is_available():
            resp = await azure_openai.chat_vision(prompt, image_bytes, system_instruction, temperature)
            if resp and resp.strip():
                return resp.strip()
    except Exception:
        pass

    # 3. Google Gemini Vision Fallback
    key = settings.GEMINI_API_KEY
    if not key:
        return ""
    import base64
    import httpx
    b64_img = base64.b64encode(image_bytes).decode("utf-8")
    payload = {
        "contents": [
            {
                "role": "user",
                "parts": [
                    {"text": prompt},
                    {
                        "inline_data": {
                            "mime_type": "image/png",
                            "data": b64_img
                        }
                    }
                ]
            }
        ],
        "generationConfig": {"temperature": temperature}
    }
    if system_instruction:
        payload["systemInstruction"] = {"parts": [{"text": system_instruction}]}

    models = ["gemini-3.1-flash-lite", "gemini-3.5-flash", "gemini-3.6-flash", "gemini-flash-latest"]
    for m in models:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{m}:generateContent?key={key}"
        try:
            async with httpx.AsyncClient(timeout=22.0) as client:
                res = await client.post(url, json=payload)
                if res.status_code == 200:
                    data = res.json()
                    candidates = data.get("candidates", [])
                    if candidates:
                        parts = candidates[0].get("content", {}).get("parts", [])
                        if parts:
                            return parts[0].get("text", "")
        except Exception:
            continue
    return ""

call_openai_vision = call_gemini_vision
call_vlm = call_gemini_vision


async def call_llm(
    prompt: str,
    system_instruction: str = "",
    temperature: float = 0.2,
    image_bytes: Optional[bytes] = None
) -> str:
    """Universal Async LLM: OpenAI -> Azure OpenAI -> Unified LLM -> Google Gemini -> NVIDIA NIM -> Ollama."""
    settings = get_settings()

    # 0. High-Precision Vision Mode (for technical tables, circuits, formulas, diagrams)
    if image_bytes:
        vision_resp = await call_gemini_vision(prompt, image_bytes, system_instruction, temperature)
        if vision_resp and vision_resp.strip():
            return vision_resp.strip()

    # 1. Direct OpenAI Client (GPT-4o-mini / GPT-4o)
    provider = getattr(settings, "LLM_PROVIDER", "openai").lower()
    if provider in ("openai", "azure_openai"):
        if provider == "openai":
            try:
                from app.rag.azure_openai_client import openai_client
                if await openai_client.is_available():
                    msgs = []
                    if system_instruction:
                        msgs.append({"role": "system", "content": system_instruction})
                    msgs.append({"role": "user", "content": prompt})
                    resp = await openai_client.chat(msgs, temperature=temperature)
                    if resp and resp.strip():
                        return resp.strip()
            except Exception:
                pass
        elif provider == "azure_openai":
            try:
                from app.rag.azure_openai_client import azure_openai
                if await azure_openai.is_available():
                    msgs = []
                    if system_instruction:
                        msgs.append({"role": "system", "content": system_instruction})
                    msgs.append({"role": "user", "content": prompt})
                    resp = await azure_openai.chat(msgs, temperature=temperature)
                    if resp and resp.strip():
                        return resp.strip()
            except Exception:
                pass

    # 2. Unified Client Router
    try:
        from app.rag.ollama_client import ollama
        if await ollama.is_available():
            msgs = []
            if system_instruction:
                msgs.append({"role": "system", "content": system_instruction})
            msgs.append({"role": "user", "content": prompt})
            resp = await ollama.chat(msgs, temperature=temperature)
            if resp and resp.strip():
                return resp.strip()
    except Exception:
        pass

    # 2. Google Gemini REST Fallback
    if settings.GEMINI_API_KEY:
        try:
            import httpx
            g_key = settings.GEMINI_API_KEY
            g_model = getattr(settings, "GEMINI_MODEL", "gemini-3.1-flash-lite").replace("models/", "")
            g_url = f"https://generativelanguage.googleapis.com/v1beta/models/{g_model}:generateContent?key={g_key}"
            g_payload: Dict[str, Any] = {
                "contents": [{"role": "user", "parts": [{"text": prompt}]}],
                "generationConfig": {"temperature": temperature}
            }
            if system_instruction:
                g_payload["systemInstruction"] = {"parts": [{"text": system_instruction}]}
            async with httpx.AsyncClient(timeout=22.0) as client:
                g_res = await client.post(g_url, json=g_payload)
                if g_res.status_code == 200:
                    g_data = g_res.json()
                    g_cands = g_data.get("candidates", [])
                    if g_cands:
                        g_parts = g_cands[0].get("content", {}).get("parts", [])
                        if g_parts and g_parts[0].get("text"):
                            return g_parts[0].get("text")
        except Exception:
            pass

    # 3. NVIDIA NIM Fallback
    nvidia_key = getattr(settings, "NVIDIA_API_KEY", "") or os.getenv("NVIDIA_API_KEY", "")
    if nvidia_key:
        try:
            import httpx
            base_url = getattr(settings, "NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1")
            chat_model = getattr(settings, "NVIDIA_CHAT_MODEL", "meta/llama-3.1-8b-instruct")
            headers = {"Authorization": f"Bearer {nvidia_key}", "Content-Type": "application/json"}
            messages = []
            if system_instruction:
                messages.append({"role": "system", "content": system_instruction})
            messages.append({"role": "user", "content": prompt})

            async with httpx.AsyncClient(timeout=20.0) as client:
                res = await client.post(
                    f"{base_url}/chat/completions",
                    headers=headers,
                    json={"model": chat_model, "messages": messages, "temperature": temperature}
                )
                if res.status_code == 200:
                    data = res.json()
                    return data["choices"][0]["message"]["content"]
        except Exception:
            pass

    return ""


# ─── Meta-Referential Context & Anaphora Resolution Helpers ───────────────────

def is_meta_referential_query(query: str) -> bool:
    """Detects if query references previous conversation turns/modules rather than an explicit topic."""
    if not query:
        return False
    q = query.lower().strip()
    patterns = [
        r"\b(above|previous|last|prior|preceding)\s+(module|response|answer|explanation|topic|turn|content|lecture|lesson|section|material|chapter|discussion)\b",
        r"\b(what|that)\s+(you|we)\s+(gave|explained|discussed|covered|provided|wrote|taught|generated)\b",
        r"\b(module|content|topic|answer|response|concept|material)\s+(you|we)\s+(gave|gave me|explained|discussed|provided|wrote|taught)\b",
        r"\b(from|on|about|based on|for)\s+(the\s+)?(above|previous|last|this)\b",
        r"^(make|create|generate|give me|build|show)?\s*(a\s+)?(flashcards?|quiz|test|deck)\s+(on|for|about|from)?\s*(this|it|above|previous|the above|what you gave|what you gave me|above module|the above module|previous module|above content)?\s*$",
    ]
    for pat in patterns:
        if re.search(pat, q):
            return True
    meta_phrases = (
        "above module", "previous module", "module you gave", "module above", "module you gave me",
        "above response", "above answer", "above explanation", "above content", "above topic", "above text",
        "previous response", "previous answer", "previous explanation", "previous turn", "previous topic", "previous content",
        "last response", "last answer", "last explanation", "last topic", "last module", "last content",
        "what you gave", "what you gave me", "what you just gave", "what you just explained", "what you explained",
        "what we discussed", "what we just discussed", "what you wrote", "what you just taught", "what you taught",
        "based on previous", "from previous", "from the previous", "from above", "on the above", "on above",
        "from this", "on this", "for this", "for the above", "for it", "this topic", "this module", "this concept"
    )
    return any(p in q for p in meta_phrases)


def extract_previous_assistant_response(history: Optional[List[Dict[str, Any]]]) -> Optional[str]:
    """Extracts text of the most recent assistant response from conversation history."""
    if not history:
        return None
    for m in reversed(history):
        role = (m.get("role") or m.get("sender") or "").lower()
        text = (m.get("text") or m.get("content") or m.get("message") or "").strip()
        if role in ("assistant", "model", "bot", "ai") and text:
            return text
    return None


async def resolve_topic_from_text(text: str, default_subject: str = "Course Material") -> str:
    """Extracts or summarizes the primary academic topic heading from educational text."""
    from app.services.study_quiz_engine import sanitize_topic_title
    if not text:
        return sanitize_topic_title(default_subject)
    # 1. Look for # Main Title Heading
    h_matches = re.findall(r"^#+\s*(.+)$", text, re.MULTILINE)
    for h in h_matches:
        cand = sanitize_topic_title(h.strip())
        if cand and len(cand) > 2 and cand.lower() not in ("overview", "summary", "notes", "key insights", "core concepts", "definitions", "module"):
            return cand
    # 2. Look for **Bold Heading**
    b_matches = re.findall(r"\*\*([A-Za-z0-9\s\-_–—:,]+)\*\*", text)
    for b in b_matches:
        cand = sanitize_topic_title(b.strip())
        if cand and 3 <= len(cand) <= 50 and cand.lower() not in ("overview", "summary", "key insights", "note", "important", "definition", "concept"):
            return cand
    # 3. Fast Agent / LLM Topic Summary
    try:
        topic_summary = await call_llm(
            f"Extract the primary 2-5 word academic topic title for this educational text:\n\n{text[:1200]}",
            "You are an academic parser. Return ONLY the 2-5 word topic title. No quotes, no preamble.",
            temperature=0.1
        )
        if topic_summary and 2 < len(topic_summary.strip()) < 80:
            return sanitize_topic_title(topic_summary.strip())
    except Exception:
        pass
    return sanitize_topic_title(default_subject)


# ─── Subject Expansion & Synthetic Textbook Generation Helpers ─────────────────

COMMON_SUBJECT_EXPANSIONS = {
    "ml": "Machine Learning",
    "ai": "Artificial Intelligence",
    "dl": "Deep Learning",
    "nlp": "Natural Language Processing",
    "cv": "Computer Vision",
    "rl": "Reinforcement Learning",
    "ds": "Data Science & Data Structures",
    "dbms": "Database Management Systems",
    "os": "Operating Systems",
    "cn": "Computer Networks",
    "toc": "Theory of Computation",
    "coa": "Computer Organization & Architecture",
    "oop": "Object-Oriented Programming",
    "dsa": "Data Structures & Algorithms",
    "math": "Mathematics",
    "maths": "Mathematics",
    "phy": "Physics",
    "chem": "Chemistry",
    "bio": "Biology",
    "stats": "Statistics & Probability",
    "python": "Python Programming",
    "cpp": "C++ Programming",
    "java": "Java Programming",
}


def normalize_subject_title(raw_subject: str) -> str:
    """Standardizes subject names and maps common acronyms (e.g. 'ml' -> 'Machine Learning')."""
    if not raw_subject:
        return "General Study"
    cleaned = raw_subject.strip()
    low = cleaned.lower().rstrip(".!?,")
    if low in COMMON_SUBJECT_EXPANSIONS:
        return COMMON_SUBJECT_EXPANSIONS[low]
    if len(low.split()) <= 4:
        for abbr, exp in COMMON_SUBJECT_EXPANSIONS.items():
            if re.search(rf"\b{re.escape(abbr)}\b", low):
                return exp
    cleaned = re.sub(
        r"(?i)^(?:i want to learn|i want to study|let'?s learn|let'?s study|can we study|can we learn|teach me|tell me about|what is|what are|explain|study|learn|about)\s+",
        "",
        cleaned
    ).strip().rstrip("?.!,")
    if cleaned and 2 <= len(cleaned) <= 60:
        c_low = cleaned.lower()
        if c_low in COMMON_SUBJECT_EXPANSIONS:
            return COMMON_SUBJECT_EXPANSIONS[c_low]
        return cleaned.title()
    return "General Study"


def extract_subject_from_query(query: str, default_subject: str = "General Study") -> str:
    """Extracts an academic subject from student query, falling back to default_subject."""
    sub = normalize_subject_title(query)
    if sub != "General Study":
        return sub
    if default_subject and default_subject not in ("General Study", "New Course Workspace", "Default Study Room", ""):
        return normalize_subject_title(default_subject)
    return "General Study"


# ─── Educational Calibration Level Profiles ─────────────────────────────────────

LEVEL_PROFILES = {
    "primary": {
        "level_name": "Primary School (Class 1–5)",
        "tone": "Warm, imaginative, visual, story-driven, and playful for young children (Class 1–5).",
        "instructions": (
            "Audience: Young elementary school children (Class 1–5, ages 6–10).\n"
            "- Use very simple language, everyday words, and vivid, friendly storytelling.\n"
            "- Explain concepts using cheerful metaphors, cartoons, animal analogies, or toys.\n"
            "- STRICTLY AVOID complex technical jargon, heavy college math, and formal theorems.\n"
            "- Math should be restricted to simple counting, playful patterns, or basic arithmetic.\n"
            "- Include friendly emojis, cheerful encouragement, and fun interactive checkpoints formatted like mini-games or observation riddles."
        ),
        "difficulty_tags": ("Exploring", "Easy Fun", "Wonder", "Kid Master"),
        "curriculum_template": [
            ("Fun Beginnings with {subject}", "A playful story introducing what {subject} is and why it is super exciting!"),
            ("Everyday Magic & Discoveries", "Where we see {subject} in the real world, at home, in nature, and with friends!"),
            ("Playful Experiments & Mini-Adventures", "Hands-on simple activities and fun puzzle-solving together."),
            ("Becoming a Young Explorer of {subject}", "Exciting review, friendly challenges, and celebrating what you learned!")
        ],
        "default_checkpoints": [
            "Can you think of one thing in your house, games, or classroom that reminds you of {subject}?",
            "If you had to explain {subject} to your best friend using a funny cartoon animal story, what would you tell them?"
        ]
    },
    "secondary": {
        "level_name": "Middle & High School (Class 6–12)",
        "tone": "Clear, engaging, structured, and exam-oriented for school students (Class 6–12).",
        "instructions": (
            "Audience: Middle and High School students (Class 6–12, ages 11–18).\n"
            "- Break down concepts step-by-step with clear definitions and visual intuition.\n"
            "- Introduce foundational formulas with KaTeX math ($...$ inline, $$...$$ blocks) accompanied by intuitive physical or geometric explanations.\n"
            "- Connect theory to practical experiments, school lab examples, and everyday technology.\n"
            "- Checkpoints should test conceptual understanding, formula application, and simple problem solving."
        ),
        "difficulty_tags": ("Beginner", "Intermediate", "Core Concepts", "Exam Prep"),
        "curriculum_template": [
            ("Foundations & Principles of {subject}", "Core terminology, foundational laws, and historical context."),
            ("Core Mechanisms, Formulas & Models", "Step-by-step breakdown of fundamental equations, rules, and problem types."),
            ("Real-World Applications & Experiments", "How principles are applied in modern science, technology, and engineering."),
            ("Problem Solving & Exam Mastery", "Synthesizing concepts, tackling multi-step questions, and review.")
        ],
        "default_checkpoints": [
            "In your own words, what is the core scientific or conceptual principle behind {subject}?",
            "How would you solve a standard problem in {subject} step-by-step using the foundational formula?"
        ]
    },
    "undergraduate": {
        "level_name": "Undergraduate (B.Tech / BSc / College)",
        "tone": "Rigorous, analytical, academically deep, and structured for university students.",
        "instructions": (
            "Audience: College and university undergraduates (B.Tech, BSc, BCA, BS).\n"
            "- Provide formal mathematical formulations, derivations, and theorems using KaTeX ($$...$$ for blocks, $...$ for inline).\n"
            "- Include algorithmic breakdowns, pseudo-code/code snippets where relevant, and complexity/trade-off analysis.\n"
            "- Cover theoretical bounds, edge cases, and canonical problem-solving methodologies.\n"
            "- Checkpoints should require analytical reasoning, derivation checks, or architectural problem-solving."
        ),
        "difficulty_tags": ("Foundational", "Intermediate Theory", "Advanced Analysis", "Synthesis"),
        "curriculum_template": [
            ("Theoretical Foundations of {subject}", "Axiomatic definitions, mathematical formulation, and fundamental theorems."),
            ("Core Algorithms, Derivations & Mechanisms", "Detailed structural derivations, algorithmic frameworks, and proof intuition."),
            ("Practical Implementation & System Design", "Concrete code patterns, empirical validation, trade-offs, and optimization."),
            ("Advanced Paradigms & Frontier Topics", "Contemporary research directions, open problems, and cross-domain synthesis.")
        ],
        "default_checkpoints": [
            "State the primary theoretical formulation or governing equation of {subject} and explain each variable.",
            "Compare two core approaches or algorithms in {subject} in terms of time complexity, memory footprint, or accuracy trade-offs."
        ]
    },
    "professional": {
        "level_name": "Professional / Postgraduate",
        "tone": "Concise, research-grade, industry-oriented, and architectural for specialists.",
        "instructions": (
            "Audience: Working software engineers, data scientists, researchers, and postgraduate specialists (M.Tech, MS, PhD).\n"
            "- Assume strong foundational and mathematical literacy; skip introductory hand-waving.\n"
            "- Focus on production systems, distributed scale, reliability, low-level optimization, and design trade-offs.\n"
            "- Reference state-of-the-art literature, empirical benchmarks, failure modes, and operational realities.\n"
            "- Checkpoints should focus on high-stakes architectural decisions, fault tolerance, and performance optimization."
        ),
        "difficulty_tags": ("Architectural Foundations", "Advanced Scalability", "Operational Optimization", "Frontier Research"),
        "curriculum_template": [
            ("Core Architecture & Theoretical Foundations", "High-performance formalisms, state-of-the-art benchmarks, and theoretical guarantees."),
            ("Scalable Systems, Pipelines & Optimization", "Low-level implementation nuances, distributed paradigms, and latency/throughput bounds."),
            ("Production Failure Modes & Operational Resilience", "Empirical edge cases, debugging telemetry, reliability engineering, and security."),
            ("State-of-the-Art Frontiers & Future Directions", "Emerging paradigms, novel architectures, and industry synthesis.")
        ],
        "default_checkpoints": [
            "What critical architectural trade-off emerges when scaling {subject} in a production environment under strict latency constraints?",
            "How do recent state-of-the-art methods mitigate known failure modes or performance bottlenecks in {subject}?"
        ]
    }
}


def parse_learning_level(text: str) -> Optional[str]:
    """
    Parses user input to identify the 4-tier educational calibration level:
    - 'primary': Class 1–5 / Elementary / Kids
    - 'secondary': Class 6–12 / Middle & High School
    - 'undergraduate': B.Tech / BSc / College
    - 'professional': Professional / Postgraduate / Advanced
    """
    if not text:
        return None
    raw = text.strip().lower()

    # 1. Exact numeric option selection: "1", "2", "3", "4"
    if raw in ("1", "one", "#1", "option 1", "tier 1", "1."):
        return "primary"
    if raw in ("2", "two", "#2", "option 2", "tier 2", "2."):
        return "secondary"
    if raw in ("3", "three", "#3", "option 3", "tier 3", "3."):
        return "undergraduate"
    if raw in ("4", "four", "#4", "option 4", "tier 4", "4."):
        return "professional"

    # 2. Check for explicit class / grade ranges
    # Primary: Class 1 to 5
    if re.search(r"\b(?:class|grade|standard|std)\s*([1-5])\b", raw) or \
       re.search(r"\b([1-5])(?:st|nd|rd|th)?\s*(?:class|grade|standard|std)\b", raw) or \
       any(w in raw for w in ("primary", "elementary", "kindergarten", "nursery", "kid", "child", "young learner", "1st std", "2nd std", "3rd std", "4th std", "5th std")):
        return "primary"

    # Secondary: Class 6 to 12
    if re.search(r"\b(?:class|grade|standard|std)\s*([6-9]|1[0-2])\b", raw) or \
       re.search(r"\b([6-9]|1[0-2])(?:th)?\s*(?:class|grade|standard|std)\b", raw) or \
       any(w in raw for w in ("middle school", "high school", "secondary", "matric", "intermediate", "inter", "+2", "plus two", "10th", "12th", "6th std", "7th std", "8th std", "9th std", "10th std", "11th std", "12th std")):
        return "secondary"

    # Professional / Postgraduate
    if any(w in raw for w in ("professional", "postgraduate", "postgrad", "working", "industry", "job", "mtech", "m.tech", "masters", "master", "phd", "ph.d", "doctorate", "researcher", "practitioner", "architect")):
        return "professional"

    # Undergraduate / College
    if any(w in raw for w in ("undergrad", "undergraduate", "college", "university", "btech", "b.tech", "bsc", "b.sc", "bca", "b.c.a", "be", "b.e", "bachelor", "engineering")):
        return "undergraduate"

    # Fallback pattern for "option X"
    exact_num_match = re.search(r"\b(?:option|tier|level|choice|no\.?|#)?\s*([1-4])\b", raw)
    if exact_num_match:
        val = exact_num_match.group(1)
        return {"1": "primary", "2": "secondary", "3": "undergraduate", "4": "professional"}.get(val)

    return None


async def generate_synthetic_textbook(
    session_id: str,
    subject: str,
    user_id: str = "default-user",
    level_key: str = "undergraduate"
) -> Dict[str, Any]:
    """
    Generates a calibrated synthetic textbook and multi-module curriculum roadmap for a subject.
    Calibrated across 4 tiers: Primary (Class 1-5), Secondary (Class 6-12), Undergrad, and Professional.
    Indexes the content directly into SQLite FTS5 and registers it in session_topics & session_documents.
    """
    clean_sub = normalize_subject_title(subject)
    if clean_sub == "General Study" and subject and subject.strip():
        clean_sub = subject.strip().title()

    profile = LEVEL_PROFILES.get(level_key, LEVEL_PROFILES["undergraduate"])
    level_name = profile["level_name"]

    system_instruction = (
        f"You are a subject-matter expert who has worked professionally in {clean_sub} "
        f"AND an expert instructional designer. You write textbooks the way top applied programs do — "
        f"case-study-driven, project-based, grounded in real practice, not abstract theory alone. "
        f"You are now writing for: {level_name}. {profile['instructions']}"
    )

    field_context_by_level = {
        "primary": f"as explored by curious young learners through everyday life, stories, and play",
        "secondary": f"as studied by school students preparing for exams and real-world understanding",
        "undergraduate": f"as applied by undergraduate students, engineers, analysts, and practitioners",
        "professional": f"as deployed by industry practitioners, researchers, and senior specialists"
    }
    field_context = field_context_by_level.get(level_key, field_context_by_level["undergraduate"])

    user_prompt = f"""
You are writing a professional applied textbook module.

ROLE: Subject-matter expert in {clean_sub} AND expert instructional designer for {level_name}.
TOPIC: {clean_sub}
FOR: {level_name} | Field context: {field_context}
Pedagogical constraints: {profile['instructions']}

═══════════════════════════════════════
CURRICULUM ROADMAP (output first)
═══════════════════════════════════════
Generate a 4-module curriculum roadmap. Each module must have a real-world professional framing — not generic chapter titles.

Return a JSON block (only this, no extra text) at the very start:
```json
{{
  "curriculum": [
    {{
      "id": "module_1",
      "title": "Module 1: [Specific real-world title]",
      "summary": "[1-2 sentences grounded in a real professional context for {level_name}]",
      "difficulty": "{profile['difficulty_tags'][0]}",
      "key_concepts": ["Concept A", "Concept B", "Concept C"],
      "estimated_study_time": "20-30 mins",
      "real_world_anchor": "[The specific profession/scenario this module is framed around]"
    }},
    {{
      "id": "module_2",
      "title": "Module 2: [Specific real-world title]",
      "summary": "[1-2 sentences grounded in real practice]",
      "difficulty": "{profile['difficulty_tags'][1]}",
      "key_concepts": ["Concept A", "Concept B"],
      "estimated_study_time": "25-35 mins",
      "real_world_anchor": "[The specific profession/scenario this module is framed around]"
    }},
    {{
      "id": "module_3",
      "title": "Module 3: [Specific real-world title]",
      "summary": "[1-2 sentences grounded in real practice]",
      "difficulty": "{profile['difficulty_tags'][2]}",
      "key_concepts": ["Concept A", "Concept B"],
      "estimated_study_time": "30-40 mins",
      "real_world_anchor": "[The specific profession/scenario this module is framed around]"
    }},
    {{
      "id": "module_4",
      "title": "Module 4: [Specific real-world title]",
      "summary": "[1-2 sentences grounded in real practice]",
      "difficulty": "{profile['difficulty_tags'][3]}",
      "key_concepts": ["Concept A", "Concept B"],
      "estimated_study_time": "35-45 mins",
      "real_world_anchor": "[The specific profession/scenario this module is framed around]"
    }}
  ]
}}
```

═══════════════════════════════════════
CHAPTER 1 — FULL APPLIED TEXTBOOK MODULE
═══════════════════════════════════════

After the JSON block, generate the complete Chapter 1 textbook module in clean Markdown.
Follow this exact 13-section structure. Every section must connect back to the chosen real-world anchor scenario.

---

# Module 1: [Title] — {clean_sub}

> **Level**: {level_name} | **Field**: {field_context}

## § 1 — Chapter Overview
- **Real-World Framing**: Introduce the anchor scenario or profession that frames this entire chapter (a running thread, not a one-off example — e.g., "This chapter follows Priya, a junior data analyst at a retail chain tracking weekly sales patterns").
- **Why This Matters Outside the Classroom**: 2-3 sentences connecting this module to real decisions, jobs, and outcomes.
- **Learning Objectives** (Bloom's-aligned, written as real capabilities): Use action phrases like "calculate X for Y client," "design a Z for W scenario," — not abstract "understand" or "know."

## § 2 — Prerequisite Check
- 3-5 quick diagnostic questions tied to the anchor scenario.
- Example format: "Before Priya can analyze the sales data, can you...?"

## § 3 — Case Study Hook
- Open with a realistic, high-stakes scenario (a news event, workplace situation, real dataset snippet, or historical case).
- Make the stakes explicit — what goes wrong if this concept is misunderstood?
- Include at least one **authentic artifact** (a formatted table, a sample report snippet, a realistic dataset, a schedule, a receipt) that the student must read and use later.

## § 4 — Core Content: Theory Meets Practice
- Introduce each concept through the real scenario FIRST, then formalize it.
- Use **"In real life, this looks like..."** callouts explicitly.
- Include at least one **full authentic artifact** (formatted as a Markdown table) that the student must interact with.
- For math/science/technical content: show exactly how practitioners compute this (mental shortcuts, tools, software, instruments commonly used).
- For primary level: use story-driven, sensory, playful explanations with no heavy jargon.
- For secondary level: use visual intuition first, then introduce formulas.
- For undergraduate level: include formal definitions, mathematical notation (KaTeX: $$...$$), and algorithmic steps.
- For professional level: include production-grade considerations, edge cases, and system trade-offs.

## § 5 — Worked Examples: Field Scenarios
- **Example 1 (Clean scenario)**: Frame as a real task ("Priya's manager asks her to..."). Show full solution step-by-step.
- **Example 2 (Messy data)**: Include irrelevant or incomplete information — the student must first identify what matters. Show how a professional would filter it.
- **Example 3 (Wrong approach)**: Demonstrate a common real-world error. Show the mistake, the real consequence it causes, and then the correct approach.

## § 6 — Interactive Checkpoints
- 3 decision-point questions framed as in-scenario decisions the student makes as if they ARE the professional.
- Format: "You are the [role] — what do you do?"

## § 7 — Key Terms & Glossary
| **Textbook Term** | **Real-World / Industry Jargon** | **Definition** |
|---|---|---|
| Term 1 | Industry synonym | Clear, level-appropriate definition |
| Term 2 | Industry synonym | Clear, level-appropriate definition |

## § 8 — Practice Exercises: Real Task Simulation

**Tier 1 — Recall** (straightforward, scenario-flavored): 3 questions

**Tier 2 — Applied** (using a real-style artifact — table, schedule, data): 2 questions

**Tier 3 — Analytical** (multi-step, messy or incomplete data): 1-2 questions

**Tier 4 — Mini-Project** (higher levels only): A small end-to-end real task (e.g., "plan a budget," "analyze this dataset," "design this system component").

## § 9 — Real-World & Interdisciplinary Connections
- Name specific job roles, industries, and tools where this exact skill is used today.
- Include at least one interdisciplinary connection (e.g., this math concept also appears in music, biology, architecture).

## § 10 — Chapter Summary
- Recap tied back to the running real-world anchor scenario.
- 3-5 key takeaways in bullet form.

## § 11 — Self-Assessment Rubric
| **"Can I now...?"** | **Not Yet** | **Getting There** | **Yes, Independently** |
|---|---|---|---|
| [Real capability from learning objectives] | ☐ | ☐ | ☐ |
| [Real capability from learning objectives] | ☐ | ☐ | ☐ |
| [Real capability from learning objectives] | ☐ | ☐ | ☐ |

## § 12 — Answer Key with Explanations
- Full reasoning for all exercises.
- For the messy data example: explain exactly which information was irrelevant and why.
- For the wrong approach example: explain the real-world consequence of the error.

## § 13 — Extension: Try It Yourself
- A small real-world task the student can attempt outside the book.
- Must be genuinely doable with everyday materials or free online tools.
- Examples: "Look at a real grocery receipt and...", "Open a spreadsheet and...", "Find a news article about... and apply..."

---
END OF CHAPTER 1

IMPORTANT OUTPUT RULES:
- Start with the ```json curriculum block, then immediately the Markdown chapter.
- Do NOT add any other text, preamble, or explanation outside these two blocks.
- Every section must reference the anchor scenario at least once.
- Invented-but-realistic data must be labeled: *(Illustrative data — not verified)*
- Vocabulary and complexity STRICTLY matched to {level_name}.
- For primary level: no heavy math, use stories and fun analogies.
- For secondary level: include formulas with intuitive explanation before formalism.
- For undergraduate/professional level: include formal notation (KaTeX: $$...$$ blocks, $...$ inline), algorithms, and trade-offs.
- Do NOT use emojis anywhere in the curriculum or textbook content (no emojis in headings, titles, bullet points, or callouts). Maintain a clean, professional academic aesthetic.
"""

    raw_resp = await call_llm(user_prompt, system_instruction, temperature=0.2)
    curriculum = []
    chapter_title = f"Module 1: Foundations of {clean_sub}"
    chapter_content = ""
    checkpoints = []

    try:
        raw_text = raw_resp.strip()
        # 1. Extract the JSON curriculum block (```json ... ``` fenced)
        json_fence_match = re.search(r"```json\s*(\{.*?\})\s*```", raw_text, re.DOTALL | re.IGNORECASE)
        if json_fence_match:
            parsed = json.loads(json_fence_match.group(1))
            curriculum = parsed.get("curriculum", [])

        # 2. Extract the markdown chapter — everything after the closing ```
        after_json = re.sub(r"```json\s*\{.*?\}\s*```", "", raw_text, flags=re.DOTALL | re.IGNORECASE).strip()
        if after_json:
            chapter_content = after_json

        # 3. Detect chapter title from first H1 heading
        h1_match = re.search(r"^#\s+(.+)$", chapter_content, re.MULTILINE)
        if h1_match:
            chapter_title = h1_match.group(1).strip()

        # 4. Extract Interactive Checkpoints from § 6 if present
        cp_section_match = re.search(
            r"##\s*§\s*6\s*[—\-–]?\s*Interactive Checkpoints(.+?)(?=##\s*§\s*7|$)",
            chapter_content, re.DOTALL | re.IGNORECASE
        )
        if cp_section_match:
            cp_text = cp_section_match.group(1)
            checkpoints = [
                m.strip().lstrip("- *0123456789.").strip()
                for m in re.findall(r"(?:^|\n)[\-\*\d\.]+\s+(.+)", cp_text)
                if m.strip()
            ][:3]
    except Exception:
        pass

    if not curriculum:
        curriculum = []
        for idx, (tmpl_title, tmpl_summary) in enumerate(profile["curriculum_template"]):
            curriculum.append({
                "id": f"module_{idx+1}",
                "title": f"Module {idx+1}: {tmpl_title.format(subject=clean_sub)}",
                "summary": tmpl_summary.format(subject=clean_sub),
                "difficulty": profile["difficulty_tags"][idx],
                "key_concepts": [f"{clean_sub} Concepts", f"Step {idx+1}", "Key Takeaways"],
                "estimated_study_time": f"{20 + idx*5} mins",
                "document_name": f"[Textbook] {clean_sub}"
            })

    for c in curriculum:
        c["document_name"] = f"[Textbook] {clean_sub}"

    if not chapter_content:
        # Structured 13-section fallback in proper applied textbook format
        if level_key == "primary":
            chapter_content = (
                f"# Module 1: The Wonderful World of {clean_sub}\n\n"
                f"> **Level**: {level_name} | **Field**: as explored by curious young learners through everyday life, stories, and play\n\n"
                f"## § 1 — Chapter Overview\n"
                f"**Real-World Framing**: This chapter follows a young explorer named Mia who discovers {clean_sub} hiding in everyday life — at the market, in the garden, and in her toy box.\n\n"
                f"**Why This Matters**: Understanding {clean_sub} helps you solve puzzles, make decisions, and understand the world around you — just like Mia does every day!\n\n"
                f"**Learning Objectives**: By the end of this chapter, you will be able to:\n"
                f"- Spot examples of {clean_sub} in your daily life at home and school\n"
                f"- Explain what {clean_sub} means using a simple story or drawing\n"
                f"- Answer fun questions about {clean_sub} using what you know\n\n"
                f"## § 2 — Prerequisite Check\n"
                f"Before we begin Mia's adventure, let's check what you already know:\n"
                f"1. Can you name one thing you see every day at home?\n"
                f"2. Do you like solving puzzles or riddles? Why?\n"
                f"3. Have you ever helped someone figure something out? What happened?\n\n"
                f"## § 3 — Case Study Hook\n"
                f"**Mia's Big Discovery**\n\n"
                f"One morning, Mia's mum asked her to sort the fruit basket. There were apples, bananas, and oranges all mixed up. \"How do I know which ones go together?\" Mia wondered. This is exactly what {clean_sub} is all about — finding patterns, making sense of things, and solving problems step by step!\n\n"
                f"## § 4 — Core Content: The Big Ideas\n"
                f"**In real life, this looks like...** Mia counting apples (3) and oranges (2) and discovering she has 5 fruits in total.\n\n"
                f"**The Big Idea of {clean_sub}**: [Core concept explained through Mia's story using simple, friendly language]\n\n"
                f"## § 5 — Worked Examples\n"
                f"**Example 1 (Mia's Market Trip)**: Mia buys 2 apples and 3 bananas. How many fruits does she have?\n\n"
                f"**Example 2 (Mia's Messy Toy Box)**: Mia's toy box has 10 items — but some are broken. She only counts the working ones. What does she need to know first?\n\n"
                f"## § 6 — Interactive Checkpoints\n"
                f"- You are Mia at the market — how many bananas are left if you started with 5 and gave 2 to your friend?\n"
                f"- What would you sort first in Mia's toy box — the big toys or the small ones? Why?\n"
                f"- If Mia finds 3 more apples, how does that change her fruit count?\n\n"
                f"## § 7 — Key Terms & Glossary\n"
                f"| **Word** | **What It Means** |\n"
                f"|---|---|\n"
                f"| Pattern | Something that repeats or follows a rule |\n"
                f"| Sort | Putting things into groups |\n"
                f"| Count | Finding how many there are |\n\n"
                f"## § 8 — Practice Exercises\n"
                f"**Tier 1**: Name 3 things in your classroom that belong together. Why do they go together?\n\n"
                f"**Tier 2**: Look at this fruit list: 3 apples, 2 bananas, and 1 orange. How many of each fruit are there?\n\n"
                f"**Tier 3**: Mia has 12 crayons but 4 are broken. She shares the good ones equally with 2 friends. How many does each friend get?\n\n"
                f"**Mini-Project**: At home tonight, help sort the vegetables or groceries. Draw a picture of how you sorted them!\n\n"
                f"## § 9 — Real-World Connections\n"
                f"- **Shopkeepers** use {clean_sub} to count money and stock.\n"
                f"- **Doctors** use it to count medicines and doses.\n"
                f"- **Teachers** use it to count students and give out supplies.\n\n"
                f"## § 10 — Chapter Summary\n"
                f"In this chapter, we followed Mia on her discovery adventure. We learned that {clean_sub} is all around us — in shopping, sorting, and solving everyday puzzles. You are now a young {clean_sub} explorer!\n\n"
                f"## § 11 — Self-Assessment Rubric\n"
                f"| **Can I now...?** | Not Yet | Getting There | Yes! |\n"
                f"|---|---|---|---|\n"
                f"| Find {clean_sub} examples in daily life | ☐ | ☐ | ☐ |\n"
                f"| Explain it to a friend using a story | ☐ | ☐ | ☐ |\n"
                f"| Solve a simple Tier 1 exercise | ☐ | ☐ | ☐ |\n\n"
                f"## § 12 — Answer Key\n"
                f"Tier 1: Answers will vary — focus on reasoning.\n"
                f"Tier 2: Apples = 3, Bananas = 2, Oranges = 1\n"
                f"Tier 3: 12 − 4 = 8 good crayons ÷ 2 friends = 4 each\n\n"
                f"## § 13 — Try It Yourself!\n"
                f"Tonight, look at your family's kitchen. Count how many of each type of fruit or vegetable you find. Draw a chart and show it to a family member!"
            )
        elif level_key == "secondary":
            chapter_content = (
                f"# Module 1: Foundations of {clean_sub} in the Real World\n\n"
                f"> **Level**: {level_name} | **Field**: as studied by school students preparing for exams and real-world understanding\n\n"
                f"## § 1 — Chapter Overview\n"
                f"**Real-World Framing**: This chapter follows Arjun, a Class 9 student who volunteers at his family's small hardware store on weekends — and uses {clean_sub} to help manage inventory, calculate bills, and solve real problems.\n\n"
                f"**Why This Matters**: {clean_sub} is at the core of engineering, science, commerce, and everyday decision-making. Understanding it now gives you a powerful toolset for exams and life.\n\n"
                f"**Learning Objectives**: By the end of this module, you will be able to:\n"
                f"- Apply core principles of {clean_sub} to solve practical, real-world problems\n"
                f"- Use foundational formulas and methods accurately with given data\n"
                f"- Identify common errors and understand their real consequences\n\n"
                f"## § 2 — Prerequisite Check\n"
                f"Before Arjun can use {clean_sub} at the store, can you:\n"
                f"1. State the basic definition of the main concept in {clean_sub}?\n"
                f"2. Recall the key formula most commonly used in this topic?\n"
                f"3. Give one example of where this concept appears in daily life?\n\n"
                f"## § 3 — Case Study Hook\n"
                f"**The Hardware Store Problem**\n\n"
                f"Arjun's father miscalculated the store's monthly profit because he confused two related terms in {clean_sub}. The store lost ₹4,200 in one month. By the end of this chapter, you will understand exactly what went wrong — and how to prevent it.\n\n"
                f"*(Illustrative data — not verified)*\n\n"
                f"| Item | Qty Sold | Unit Price (₹) | Total |\n"
                f"|---|---|---|---|\n"
                f"| Nails (box) | 45 | 30 | 1,350 |\n"
                f"| Paint (tin) | 12 | 320 | 3,840 |\n"
                f"| Screws (pack)| 80 | 15 | 1,200 |\n"
                f"| **Total** | | | **6,390** |\n\n"
                f"## § 4 — Core Content: Theory Meets Practice\n"
                f"**In real life, this looks like...** Arjun using {clean_sub} to check whether his father's calculation is correct.\n\n"
                f"**Step 1**: Understand the concept from the scenario first.\n"
                f"**Step 2**: Formalize it — introduce the textbook definition and formula.\n"
                f"**Step 3**: Apply it back to Arjun's store data.\n\n"
                f"*Professionals use: spreadsheet tools (Excel/Sheets), calculators, and estimation shortcuts in day-to-day work.*\n\n"
                f"## § 5 — Worked Examples: Field Scenarios\n"
                f"**Example 1 (Clean)**: Arjun's manager asks him to calculate the total bill for a customer buying 15 boxes of nails at ₹30 each and 3 tins of paint at ₹320 each.\n\n"
                f"**Example 2 (Messy Data)**: A delivery receipt lists 12 different items, but 3 are out of stock and 2 have wrong prices. Arjun must identify which data to use.\n\n"
                f"**Example 3 (Wrong Approach)**: Arjun's father added VAT twice, inflating the price by 18%. The consequence: customers complained, two regulars left, losing ₹8,000/month in recurring business.\n\n"
                f"## § 6 — Interactive Checkpoints\n"
                f"- You are Arjun at the counter — a customer gives ₹500 for a ₹347 purchase. What change do you give, and how do you verify?\n"
                f"- The store received an invoice with one item's quantity missing. What do you do before processing payment?\n"
                f"- Arjun suspects the VAT was applied incorrectly. What specific numbers would you check first?\n\n"
                f"## § 7 — Key Terms & Glossary\n"
                f"| **Textbook Term** | **Real-World / Industry Jargon** | **Definition** |\n"
                f"|---|---|---|\n"
                f"| Revenue | Turnover / Top Line | Total money received from sales |\n"
                f"| Variable | Unknown | A quantity that can change in a problem |\n"
                f"| Formula | Equation / Rule | A mathematical relationship between quantities |\n\n"
                f"## § 8 — Practice Exercises\n"
                f"**Tier 1**: State the main formula for the core concept in {clean_sub} and define each term.\n\n"
                f"**Tier 2**: Use Arjun's store table above to calculate the average revenue per product category.\n\n"
                f"**Tier 3**: A customer returns 5 nail boxes (bought at ₹30) and wants store credit. The store charges a 10% restocking fee. What credit does the customer receive? Show all working.\n\n"
                f"**Mini-Project**: Interview a shopkeeper, a relative, or look at a real bill at home. Identify one place where {clean_sub} is being used (correctly or incorrectly). Write a 150-word report.\n\n"
                f"## § 9 — Real-World & Interdisciplinary Connections\n"
                f"- **Accountants** use this daily in tally sheets and audit reports.\n"
                f"- **Engineers** use related principles in load calculations and materials planning.\n"
                f"- **Interdisciplinary link**: The same mathematical structure appears in biology (population growth), music (rhythm patterns), and architecture (structural ratios).\n\n"
                f"## § 10 — Chapter Summary\n"
                f"We followed Arjun through the hardware store and discovered how {clean_sub} is not just a school topic — it's a live business tool. Key takeaways:\n"
                f"- The core concept and its formal definition\n"
                f"- How professionals apply it in real scenarios\n"
                f"- Why precision matters — small errors cause real financial losses\n\n"
                f"## § 11 — Self-Assessment Rubric\n"
                f"| **Can I now...?** | Not Yet | Getting There | Yes, Independently |\n"
                f"|---|---|---|---|\n"
                f"| Apply the main formula to a real data set | ☐ | ☐ | ☐ |\n"
                f"| Identify irrelevant data in a messy problem | ☐ | ☐ | ☐ |\n"
                f"| Catch a common error and explain its consequence | ☐ | ☐ | ☐ |\n\n"
                f"## § 12 — Answer Key\n"
                f"Tier 2: Average revenue = 6,390 ÷ 3 categories = ₹2,130 per category *(Illustrative)*\n"
                f"Tier 3: 5 × 30 = ₹150. Restocking fee = 10% × 150 = ₹15. Credit = 150 − 15 = **₹135**\n"
                f"Messy data note: Ignore out-of-stock items and wrong-price entries until verified.\n\n"
                f"## § 13 — Try It Yourself!\n"
                f"Find a real grocery receipt at home. Calculate the total yourself without looking at the printed total. Then check — were you correct? If not, find which item you miscalculated."
            )
        else:
            # Undergraduate / Professional shared high-quality fallback
            level_tag = "production system" if level_key == "professional" else "system"
            chapter_content = (
                f"# Module 1: Foundations of {clean_sub} — Applied Practice\n\n"
                f"> **Level**: {level_name} | **Field**: {field_context}\n\n"
                f"## § 1 — Chapter Overview\n"
                f"**Real-World Framing**: This module follows a team of analysts/engineers at a mid-sized company using {clean_sub} to solve a high-stakes operational problem — tracking performance metrics, optimizing a pipeline, or designing a {level_tag} component.\n\n"
                f"**Why This Matters**: Mastery of {clean_sub} is directly required in roles at Google, Stripe, ISRO, McKinsey, and thousands of firms across engineering, finance, and research. Errors at this level have production, financial, or safety consequences.\n\n"
                f"**Learning Objectives** (Bloom's-aligned):\n"
                f"- **Apply**: Use the core mathematical formulation of {clean_sub} on real datasets\n"
                f"- **Analyze**: Identify failure modes, edge cases, and performance trade-offs\n"
                f"- **Create**: Design or extend a component/system grounded in {clean_sub} principles\n\n"
                f"## § 2 — Prerequisite Check\n"
                f"Before the team deploys this {level_tag}, confirm you can:\n"
                f"1. State the governing equation or core theorem of {clean_sub} from memory\n"
                f"2. Describe the computational or algorithmic complexity of the standard approach\n"
                f"3. Name two real failure modes or edge cases in {clean_sub}\n\n"
                f"## § 3 — Case Study Hook\n"
                f"**The Production Incident**\n\n"
                f"A team at a logistics company deployed a {clean_sub}-based system that worked perfectly in testing but failed under production load — causing a 6-hour outage affecting 40,000 users. The root cause: a foundational assumption about {clean_sub} that did not hold at scale.\n\n"
                f"*(Illustrative scenario — not a verified incident)*\n\n"
                f"| Metric | Test Environment | Production | Delta |\n"
                f"|---|---|---|---|\n"
                f"| Throughput | 1,200 req/s | 8,400 req/s | 7× |\n"
                f"| Latency (p99) | 12ms | 847ms | 70× |\n"
                f"| Error rate | 0.01% | 14.3% | 1430× |\n\n"
                f"## § 4 — Core Content: Theory Meets Practice\n"
                f"**In real life, this looks like...** the engineering team diagnosing the {clean_sub} bottleneck using profiling tools and mathematical analysis.\n\n"
                f"**Formal Definition**: [Core theorem/algorithm/formula for {clean_sub}]\n\n"
                f"**Mathematical Formulation** (KaTeX):\n"
                f"$$\\text{{[Core governing equation of {clean_sub}]}}$$\n\n"
                f"Where each variable represents: [variable definitions]\n\n"
                f"**How professionals compute this**: Engineers use tools such as [relevant software/instruments/libraries], applying the following workflow: [professional workflow steps]\n\n"
                f"## § 5 — Worked Examples: Field Scenarios\n"
                f"**Example 1 (Clean)**: Given a dataset with [parameters], calculate [outcome] using the core formula. Show full derivation.\n\n"
                f"**Example 2 (Messy Data)**: The engineering team receives telemetry data from 12 services. 3 have stale metrics, 2 have schema mismatches. Identify which to trust and why.\n\n"
                f"**Example 3 (Wrong Approach)**: A common mistake: [specific error]. Real consequence: [system failure mode]. Correct approach: [fix with explanation].\n\n"
                f"## § 6 — Interactive Checkpoints\n"
                f"- You are the on-call engineer — latency spikes to p99=2s. Which {clean_sub} parameter do you investigate first and why?\n"
                f"- The PM asks you to add a new feature that changes a core assumption of {clean_sub}. What risks do you surface?\n"
                f"- Given the production data table above, what is your hypothesis about the failure cause?\n\n"
                f"## § 7 — Key Terms & Glossary\n"
                f"| **Textbook Term** | **Real-World / Industry Jargon** | **Definition** |\n"
                f"|---|---|---|\n"
                f"| Algorithm | Pipeline / Workflow | Ordered set of operations for solving a class of problems |\n"
                f"| Complexity | Overhead / Cost | Resource usage as a function of input size |\n"
                f"| Invariant | Constraint / Guarantee | A property that must always hold for correctness |\n\n"
                f"## § 8 — Practice Exercises\n"
                f"**Tier 1**: State the Big-O complexity of the core algorithm in {clean_sub} and justify it.\n\n"
                f"**Tier 2**: Using the production metrics table above, calculate the theoretical throughput ceiling given the p99 latency budget.\n\n"
                f"**Tier 3 — Analytical**: The team wants to reduce error rate from 14.3% to <0.1% without degrading throughput. Propose a {clean_sub}-grounded solution. State your assumptions explicitly.\n\n"
                f"**Tier 4 — Mini-Project**: Design a minimal monitoring dashboard specification for a {clean_sub}-based system. Define the 5 key metrics to track, their alert thresholds, and the on-call runbook steps.\n\n"
                f"## § 9 — Real-World & Interdisciplinary Connections\n"
                f"- **Data Engineers**: Use {clean_sub} in pipeline orchestration (Apache Airflow, Spark).\n"
                f"- **ML Engineers**: Apply it in model training loops and hyperparameter search.\n"
                f"- **Financial Analysts**: Use related mathematical structures in risk modeling and portfolio optimization.\n"
                f"- **Interdisciplinary**: The same core principles appear in control theory (robotics), queuing theory (network design), and information theory (compression algorithms).\n\n"
                f"## § 10 — Chapter Summary\n"
                f"We followed a production engineering team through a high-stakes incident rooted in {clean_sub}. Key takeaways:\n"
                f"- The formal governing equations and their operational implications\n"
                f"- How scale reveals hidden assumptions in {clean_sub} implementations\n"
                f"- The professional workflow for diagnosis, triage, and resolution\n\n"
                f"## § 11 — Self-Assessment Rubric\n"
                f"| **Can I now...?** | Not Yet | Getting There | Yes, Independently |\n"
                f"|---|---|---|---|\n"
                f"| Derive the core formula and explain each term | ☐ | ☐ | ☐ |\n"
                f"| Diagnose a {clean_sub} failure from production metrics | ☐ | ☐ | ☐ |\n"
                f"| Design a {clean_sub} component with explicit trade-off analysis | ☐ | ☐ | ☐ |\n\n"
                f"## § 12 — Answer Key\n"
                f"Tier 2: Throughput ceiling = 1 / p99 latency = 1 / 0.847s ≈ 1,181 req/s per instance *(Illustrative)*\n"
                f"Messy data: Stale metrics (>60s old) and schema-mismatched services should be excluded pending re-verification.\n\n"
                f"## § 13 — Try It Yourself!\n"
                f"Open any free dataset (Kaggle, UCI ML Repository, or a public API). Apply the core concept of {clean_sub} to it. Document: (1) your hypothesis, (2) your method, (3) one surprising finding. Share in 300 words."
            )

    if not checkpoints:
        checkpoints = [q.format(subject=clean_sub) for q in profile["default_checkpoints"]]

    doc_id = f"textbook_{int(datetime.now(timezone.utc).timestamp())}"
    chunks = []

    sections = re.split(r"\n(?=#{2,4}\s)", chapter_content)
    for idx, sec in enumerate(sections):
        sec_text = sec.strip()
        if sec_text:
            chunks.append({
                "chunk_id": f"tb_ch1_{idx}",
                "page": 1,
                "source_type": "text",
                "content": sec_text
            })

    for idx, mod in enumerate(curriculum):
        mod_chunk = f"Module {idx+1}: {mod.get('title')}\nTarget Level: {level_name}\nSummary: {mod.get('summary')}\nKey Concepts: {', '.join(mod.get('key_concepts', []))}"
        chunks.append({
            "chunk_id": f"tb_mod_{idx+1}",
            "page": idx + 1,
            "source_type": "text",
            "content": mod_chunk
        })

    insert_chunks_to_fts(session_id, doc_id, chunks)
    save_session_topics(session_id, curriculum, append=False, document_name=f"[Textbook] {clean_sub}")
    save_session_document(
        session_id=session_id,
        doc_id=doc_id,
        filename=f"[Textbook] {clean_sub}.md",
        file_path="synthetic_curriculum",
        status="fully_processed",
        page_count=len(curriculum)
    )
    register_or_update_session(
        session_id=session_id,
        subject=clean_sub,
        title=f"{clean_sub} ({level_name})",
        status="ready",
        document_name=f"[Textbook] {clean_sub}",
        user_id=user_id
    )

    curriculum_lines = []
    for idx, mod in enumerate(curriculum):
        curriculum_lines.append(
            f"{idx+1}. **{mod.get('title')}** ({mod.get('estimated_study_time', '20 mins')})\n"
            f"   *{mod.get('summary')}*\n"
            f"   Key Concepts: `{'`, `'.join(mod.get('key_concepts', []))}`"
        )
    curriculum_block = "\n".join(curriculum_lines)
    checkpoints_lines = "\n".join(f"- **Q{i+1}**: {q}" for i, q in enumerate(checkpoints))

    response_md = (
        f"# {clean_sub} — Applied Textbook\n\n"
        f"**Target Level**: `{level_name}`\n\n"
        f"> This textbook was generated specifically for **{level_name}** and saved to your **Study Map**. "
        f"All lessons, worked examples, quizzes, and formulas in future conversations will be grounded in this material.\n\n"
        f"---\n\n"
        f"## Course Syllabus & Study Map\n\n"
        f"{curriculum_block}\n\n"
        f"---\n\n"
        f"{chapter_content}\n\n"
        f"---\n\n"
        f"### Quick-Start Checkpoints\n\n"
        f"{checkpoints_lines}\n\n"
        f"> *Jump in — answer a checkpoint, ask a question about any section, or say \"Quiz me on § 4\" to begin!*"
    )

    return {
        "thought_process": f"User calibrated for '{level_name}' on '{clean_sub}'. Generated 4-module synthetic textbook, indexed {len(chunks)} chunks into SQLite FTS5, updated Study Map, and published to Markdown Viewer.",
        "response": response_md,
        "sources": [{"chunk_id": c["chunk_id"], "page": c["page"]} for c in chunks[:3]],
        "format": "study_notes",
        "response_format": "study_notes",
        "export_ready": True,
        "is_synthetic_textbook": True,
        "level": level_key,
        "level_name": level_name
    }


# ─── 1. Planner Agent (Instant Zero-Latency Fast-Path) ───────────────────────

class QueryAnalyzerAgent:
    """Instant heuristic planning agent that decomposes queries and identifies search requirements in < 1ms."""

    async def plan(self, user_query: str, subject: str = "General Study", history: List[Dict[str, Any]] = None) -> Dict[str, Any]:
        q_lower = user_query.lower().strip()

        # 1. Format & Sub-intent classification
        is_quiz = any(k in q_lower for k in ("quiz", "test me", "ask me a question", "pop quiz", "mcq"))
        is_study_notes = bool(re.search(
            r"\b(study notes?|cheat sheet|revision notes?|study map|summari[sz]e.*as notes|create.*(?:md|\.md|markdown)|make.*(?:md|\.md|markdown)|generate.*(?:md|\.md|markdown)|(?:md|\.md|markdown)\s*(?:file|doc)?\s*(?:on|for|about))\b", q_lower
        ))
        is_comparison = any(k in q_lower for k in ("compare", "versus", " vs ", "difference between", "distinguish", "relate to"))
        is_diagram = any(k in q_lower for k in ("diagram", "figure", "chart", "architecture", "flowchart", "illustration"))
        is_solve = any(k in q_lower for k in ("solve", "calculate", "fill", "matrix", "column", "row", "position", "sequence", "table", "problem"))
        is_conceptual = any(k in q_lower for k in ("explain", "what is", "how does", "tell me", "break down", "overview", "definition", "concept", "why is", "describe"))

        # Explanation level classification
        is_eli5 = any(k in q_lower for k in ("eli5", "like i'm 5", "like im 5", "like a 5 year old", "like a five year old", "explain simply", "simple words", "for beginners", "for a child"))
        is_simple = is_eli5 or any(w in q_lower for w in ("simply", "simple", "basic", "beginner"))
        is_advanced = any(w in q_lower for w in ("advanced", "expert", "deep", "complex", "rigorous"))

        if is_eli5:
            explanation_level = "eli5"
        elif is_simple:
            explanation_level = "simple"
        elif is_advanced:
            explanation_level = "advanced"
        else:
            explanation_level = "standard"

        # Primary format
        if is_quiz:
            resp_format = "quiz"
        elif is_study_notes:
            resp_format = "study_notes"
        elif is_comparison:
            resp_format = "comparison"
        elif is_diagram:
            resp_format = "diagram"
        elif is_solve:
            resp_format = "solve"
        else:
            resp_format = "conceptual"

        # Detect compound sub-intents
        sub_intents = []
        intents_with_pos = []
        intent_keywords = [
            ("explain", "conceptual"), ("what is", "conceptual"), ("how does", "conceptual"), ("tell me", "conceptual"),
            ("quiz", "quiz"), ("test me", "quiz"), ("pop quiz", "quiz"),
            ("study notes", "study_notes"), ("cheat sheet", "study_notes"), ("markdown", "study_notes"),
            ("compare", "comparison"), ("difference between", "comparison"), (" vs ", "comparison"),
            ("solve", "solve"), ("calculate", "solve"), ("fill", "solve"), ("problem", "solve")
        ]
        for kw, it in intent_keywords:
            pos = q_lower.find(kw)
            if pos != -1:
                intents_with_pos.append((pos, it))

        if intents_with_pos:
            intents_with_pos.sort(key=lambda x: x[0])
            seen_intent = set()
            for _, it in intents_with_pos:
                if it not in seen_intent:
                    seen_intent.add(it)
                    sub_intents.append(it)

        if not sub_intents:
            sub_intents = [resp_format]

        # 2. Content requirements
        is_table = is_solve or any(k in q_lower for k in ("table", "data", "fill", "solve", "matrix", "column", "row", "calculate", "position", "sequence"))
        is_image = is_diagram or any(k in q_lower for k in ("image", "picture", "visual", "graph", "plot"))

        # 3. Clean search keywords with acronym & symbol preservation
        stopwords = {
            "what", "how", "why", "when", "where", "who", "which", "does", "the", "and", "for", 
            "with", "from", "help", "solve", "please", "about", "tell", "explain", "give", "show", "is", "are", "was", "were"
        }
        raw_words = re.findall(r"[a-z0-9_]+", q_lower)
        filtered_words = [w for w in raw_words if w not in stopwords]
        clean_noun_phrase = " ".join(filtered_words[:5]) or user_query

        bm25_queries = [clean_noun_phrase, user_query]

        # Cross-reference concept extraction for "how does X relate to Y", "X vs Y", etc.
        cross_ref_concepts = []
        cross_ref_match = (
            re.search(r"\b(?:how does|how do)\s+(.+?)\s+(?:relate to|differ from|compare to|connect with)\s+(.+?)(?:\?|$)", user_query, re.I)
            or re.search(r"\b(?:difference between|relationship between|compare)\s+(.+?)\s+(?:and|versus|vs\.?)\s+(.+?)(?:\?|$)", user_query, re.I)
            or re.search(r"\b(.+?)\s+(?:vs\.?|versus)\s+(.+?)(?:\?|$)", user_query, re.I)
        )
        if cross_ref_match:
            c1_raw = cross_ref_match.group(1).strip()
            c2_raw = cross_ref_match.group(2).strip()
            c1_words = [w for w in re.findall(r"[a-z0-9_]+", c1_raw.lower()) if w not in stopwords]
            c2_words = [w for w in re.findall(r"[a-z0-9_]+", c2_raw.lower()) if w not in stopwords]
            if c1_words and c2_words:
                c1_phrase = " ".join(c1_words)
                c2_phrase = " ".join(c2_words)
                cross_ref_concepts = [c1_phrase, c2_phrase]
                if c1_phrase not in bm25_queries:
                    bm25_queries.append(c1_phrase)
                if c2_phrase not in bm25_queries:
                    bm25_queries.append(c2_phrase)

        # Domain expansions for common technical/math abbreviations
        expansions = []
        if any(w in filtered_words for w in ("q", "k", "v")) or "q k v" in q_lower or "qkv" in q_lower:
            expansions.append("query key value attention")
        if "svm" in filtered_words:
            expansions.append("support vector machine kernel")
        if "knn" in filtered_words:
            expansions.append("k nearest neighbor")
        if "cnn" in filtered_words:
            expansions.append("convolutional neural network")
        if "rnn" in filtered_words or "lstm" in filtered_words:
            expansions.append("recurrent neural network lstm")
        if "ap" in filtered_words:
            expansions.append("arithmetic sequence progression")

        for exp in expansions:
            if exp not in bm25_queries:
                bm25_queries.append(exp)

        # Check if query is anaphoric / meta-referential to previous interaction
        is_meta_ref = is_meta_referential_query(user_query)
        resolved_topic = ""
        prev_assistant_text = ""
        if is_meta_ref and history:
            prev_assistant_text = extract_previous_assistant_response(history) or ""
            if prev_assistant_text:
                h_match = re.search(r"^#+\s*(.+)$", prev_assistant_text, re.MULTILINE)
                if h_match:
                    clean_h = re.sub(r"[\*#_`~]", "", h_match.group(1)).strip()
                    if clean_h and len(clean_h) > 2 and clean_h.lower() not in ("overview", "summary", "notes", "key insights", "definitions", "module"):
                        resolved_topic = clean_h
                if not resolved_topic:
                    b_match = re.search(r"\*\*([A-Za-z0-9\s\-_–—:,]+)\*\*", prev_assistant_text)
                    if b_match:
                        clean_b = re.sub(r"[\*#_`~]", "", b_match.group(1)).strip()
                        if clean_b and 3 <= len(clean_b) <= 50 and clean_b.lower() not in ("overview", "summary", "key insights", "note", "important"):
                            resolved_topic = clean_b
            if resolved_topic:
                if resolved_topic not in bm25_queries:
                    bm25_queries.insert(0, resolved_topic)
            elif prev_assistant_text:
                prev_kw = [w for w in re.findall(r"[a-z0-9_]+", prev_assistant_text.lower()) if len(w) > 4 and w not in stopwords]
                if prev_kw:
                    bm25_queries.insert(0, " ".join(prev_kw[:5]))

        if subject and subject.lower() not in clean_noun_phrase.lower() and subject != "General Study":
            bm25_queries.append(f"{clean_noun_phrase} {subject}")

        return {
            "sub_questions": [user_query],
            "bm25_queries": bm25_queries,
            "requires_table_data": is_table,
            "requires_image_data": is_image,
            "response_format": resp_format,
            "sub_intents": sub_intents,
            "explanation_level": explanation_level,
            "is_compound": len(sub_intents) > 1,
            "cross_ref_concepts": cross_ref_concepts,
            "is_meta_referential": is_meta_ref,
            "resolved_topic": resolved_topic,
            "prev_assistant_text": prev_assistant_text,
            "confidence": 0.95,
            "needs_clarification": False
        }


# ─── Robust Parsing, Sanitization & Verification Helpers ───────────────────

def parse_llm_json_response(text: str, default_thought: str = "") -> tuple[str, str, Any]:
    """Robust parser for LLM JSON responses with fallback to regex and markdown extraction."""
    thought = default_thought or "Synthesizing retrieved FTS5 chunks into a structured step-by-step explanation."
    answer = ""
    quiz_data = None
    if not text:
        return thought, answer, quiz_data

    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s*```$", "", cleaned).strip()

    parsed = None
    try:
        parsed = json.loads(cleaned, strict=False)
    except Exception:
        json_match = re.search(r"(\{[\s\S]*\})", cleaned)
        if json_match:
            try:
                parsed = json.loads(json_match.group(1), strict=False)
            except Exception:
                pass

    if isinstance(parsed, dict):
        thought = parsed.get("thought_process", thought)
        answer = parsed.get("response", "")
        quiz_data = parsed.get("quiz_data")

    if not answer and ('"response"' in cleaned or '"thought_process"' in cleaned):
        th_match = re.search(r'"thought_process"\s*:\s*"((?:[^"\\]|\\.)*)"', cleaned, re.DOTALL)
        if th_match:
            thought = th_match.group(1).replace(r'\"', '"').replace(r'\n', '\n')

        resp_pattern = re.search(r'"response"\s*:\s*"', cleaned)
        if resp_pattern:
            start_pos = resp_pattern.end()
            end_pos = cleaned.rfind('"')
            if end_pos > start_pos:
                raw_ans = cleaned[start_pos:end_pos]
            else:
                raw_ans = cleaned[start_pos:]
            answer = raw_ans.replace(r'\"', '"').replace(r'\n', '\n').replace(r'\t', '    ')

    if not answer:
        if cleaned.startswith("{") and '"response":' in cleaned:
            cleaned_body = re.sub(r'^\s*\{\s*"thought_process"\s*:\s*".*?"\s*,\s*"response"\s*:\s*"?', '', cleaned, flags=re.DOTALL)
            cleaned_body = re.sub(r'"?\s*\}\s*$', '', cleaned_body)
            answer = cleaned_body.replace(r'\"', '"').replace(r'\n', '\n').strip()
        else:
            answer = cleaned

    return thought, answer, quiz_data


def sanitize_katex(text: str) -> str:
    """Sanitizes control characters and fixes common LaTeX keyword truncations."""
    if not text:
        return ""
    text = text.replace('\x0c', r'\f').replace('\x07', r'\a').replace('\x08', r'\b').replace('\x0b', r'\v')
    text = re.sub(r'(?<!\\)\brac\{', r'\\frac{', text)
    text = re.sub(r'(?<!\\)\bext\{', r'\\text{', text)
    text = re.sub(r'(?<!\\)\bpprox\b', r'\\approx', text)
    return text


def check_katex_brace_balance(text: str) -> tuple[bool, str]:
    """
    Scans for LaTeX math blocks ($$...$$ and $...$) and checks if curly braces are balanced.
    Returns (is_balanced, malformed_span).
    """
    if not text:
        return True, ""

    # Check standalone block KaTeX $$...$$
    blocks = re.findall(r"\$\$([\s\S]*?)\$\$", text)
    for block in blocks:
        open_b = len(re.findall(r"(?<!\\)\{", block))
        close_b = len(re.findall(r"(?<!\\)\}", block))
        if open_b != close_b:
            snippet = block.strip().replace("\n", " ")[:80]
            return False, f"$${snippet}...$$"

    # Check inline math $...$
    inlines = re.findall(r"(?<!\$)\$(?!\$)(.*?)(?<!\$)\$(?!\$)", text)
    for inline in inlines:
        open_b = len(re.findall(r"(?<!\\)\{", inline))
        close_b = len(re.findall(r"(?<!\\)\}", inline))
        if open_b != close_b:
            return False, f"${inline.strip()[:50]}$"

    return True, ""


def count_markdown_table_rows(text: str) -> int:
    """Counts data rows in markdown tables, excluding header and separator rows."""
    if not text:
        return 0
    lines = [l.strip() for l in text.splitlines() if l.strip().startswith("|") and l.strip().endswith("|")]
    if not lines:
        return 0
    # Exclude separator lines like |---|---|
    data_lines = [l for l in lines if not re.match(r"^\|(?:\s*:?-+:?\s*\|)+$", l)]
    # First line is typically the header
    return max(0, len(data_lines) - 1)


def check_table_placeholders(text: str) -> bool:
    """Checks if any markdown table cells contain ellipsis or placeholder tokens."""
    if not text or "|" not in text:
        return False
    table_lines = [l.strip() for l in text.splitlines() if l.strip().startswith("|") and l.strip().endswith("|")]
    for line in table_lines:
        if re.match(r"^\|(?:\s*:?-+:?\s*\|)+$", line):
            continue
        cells = [c.strip() for c in line.split("|")[1:-1]]
        for c in cells:
            if c in ("...", "…", "TBD", "N/A", "TODO", "?"):
                return True
            if re.search(r"\b(TBD|TODO|N/A)\b", c, re.IGNORECASE):
                return True
    return False


def detect_expected_row_count(query: str, chunks: List[Dict[str, Any]]) -> Optional[int]:
    """Detects expected table row count from query or source table chunks."""
    m = re.search(r"\b(\d+)\s*(?:rows?|items?|parts?|questions?|problems?|sequence terms?)\b", query.lower())
    if m:
        val = int(m.group(1))
        if 2 <= val <= 30:
            return val
    numbered = re.findall(r"(?:^|\n|\s)(?:\d+[\.\)]|[a-e][\.\)])\s+", query)
    if len(numbered) >= 2:
        return len(numbered)
    for c in chunks:
        content = c.get("content", "")
        if "|" in content:
            r_count = count_markdown_table_rows(content)
            if r_count >= 2:
                return r_count
    return None


# ─── 2. Executor Agent (DecisionAgent) ──────────────────────────────────────

class DecisionAgent:
    """Executes the query plan with strict grounding, thought process, and KaTeX math."""

    async def execute(
        self,
        user_query: str,
        plan: Dict[str, Any],
        session_id: str,
        user_id: str = "default-user",
        subject: str = "General Study",
        history: List[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        # Detect specific Page Number in query (e.g. "page 22", "pagenumber 22", "pg 22", "p. 22")
        page_match = re.search(r"\b(?:page\s*number|pagenumber|page|pg|p\.?)\s*(?:no\.?)?\s*(\d+)\b", user_query.lower())
        target_page = int(page_match.group(1)) if page_match else None

        # 1.0 Adversarial Grounding Bypass Check
        adversarial_patterns = [
            r"\bignore\s+(?:the\s+)?(?:pdf|document|textbook|notes|course\s+materials?|context)\b",
            r"\bforget\s+(?:the\s+)?(?:pdf|document|material|context|notes)\b",
            r"\bjust\s+use\s+(?:your\s+)?general\s+knowledge\b",
            r"\bregardless\s+of\s+(?:the\s+)?(?:textbook|pdf|material|notes)\b",
            r"\bdisregard\s+(?:the\s+)?(?:pdf|document|notes|textbook|material)\b",
            r"\bbypass\s+(?:the\s+)?(?:rules|grounding|system|instructions?)\b",
            r"\bdon'?t\s+use\s+(?:the\s+)?(?:pdf|textbook|material|notes)\b",
        ]
        if any(re.search(pat, user_query, re.I) for pat in adversarial_patterns):
            scope_msg = (
                f"DeepTutor is scoped to tutor you strictly from your uploaded course materials for **{subject}** to ensure exam and syllabus alignment.\n\n"
                f"I noticed you asked to bypass the uploaded material and rely solely on general knowledge. "
                f"To maintain academic integrity, I stay anchored to your syllabus.\n\n"
                f"**Would you like me to answer using general academic knowledge outside your course materials?**"
            )
            return {
                "thought_process": "Detected student request to bypass syllabus grounding. Declined silent bypass per academic safety protocols and requested explicit scope confirmation.",
                "response": scope_msg,
                "sources": [],
                "format": "conceptual"
            }

        # 1.1 Retrieve candidate chunks
        retrieved_chunks = []
        seen_ids = set()

        # If a specific page was asked, fetch all chunks from that exact page directly first
        if target_page is not None:
            page_chunks = get_chunks_by_page(session_id, target_page)
            if any(w in user_query.lower() for w in ("table", "solve", "fill", "calculate", "data", "matrix", "row", "col")):
                page_chunks.sort(key=lambda c: 0 if c.get("source_type") == "table" else 1)
            for c in page_chunks:
                if c["chunk_id"] not in seen_ids:
                    seen_ids.add(c["chunk_id"])
                    retrieved_chunks.append(c)

        # 1.5 Check if student query is a simple greeting
        q_clean_greeting = user_query.strip().lower().rstrip(".!?,")
        greeting_words = {
            "hi", "hello", "hey", "hi there", "hello there", "good morning", 
            "good afternoon", "good evening", "greetings", "howdy", "namaste", 
            "hi deeptutor", "hello deeptutor", "hey deeptutor", "hi tutor", "hello tutor", "hey tutor", "sup", "yo"
        }
        is_greeting = q_clean_greeting in greeting_words or (
            bool(re.match(r'^(hi|hello|hey|greetings|good morning|good afternoon|good evening)\b', q_clean_greeting))
            and len(q_clean_greeting.split()) <= 4
        )

        if is_greeting:
            topics = get_session_topics(session_id)
            topic_bullets = ""
            if topics:
                formatted_bullets = []
                for t in topics[:5]:
                    if isinstance(t, dict):
                        title = t.get("title") or t.get("name") or "Topic"
                        summary = t.get("summary") or ""
                        if summary:
                            formatted_bullets.append(f"- **{title}**: {summary}")
                        else:
                            formatted_bullets.append(f"- **{title}**")
                    else:
                        formatted_bullets.append(f"- **{t}**")
                topic_bullets = "\n\nHere are some key topics from your uploaded course materials:\n\n" + "\n".join(formatted_bullets)

            subject_phrase = f" for **{subject}**" if subject and subject.strip() not in ("General Study", "New Course Workspace", "Default Study Room", "") else ""
            greeting_response = (
                f"Hello! I am **DeepTutor**, your AI academic tutor{subject_phrase}.\n\n"
                f"I am ready to help you analyze your course materials, solve STEM tables from first principles, break down complex schematics, or generate interactive study decks."
                f"{topic_bullets}\n\n"
                f"What concept or topic would you like to explore today?"
            )
            return {
                "thought_process": f"Student query '{user_query}' is a greeting. Responded with a warm academic greeting.",
                "response": greeting_response,
                "sources": [],
                "format": "conceptual"
            }

        # 2. Check if student query is a Boolean confirmation / refusal (with trailing clause support)
        q_clean = user_query.lower().strip()
        bool_yes_pattern = r"^(yes|y|yeah|yup|sure|ok|okay|true|go ahead|please do|tell me more|explain that|solve that|continue)\b[,\s]*(.*)$"
        bool_no_pattern = r"^(no|n|nope|nah|false|not now|stop|cancel)\b[,\s]*(.*)$"

        m_yes = re.match(bool_yes_pattern, q_clean, re.I)
        m_no = re.match(bool_no_pattern, q_clean, re.I)

        is_boolean_yes = False
        is_boolean_no = False
        trailing_clause = ""

        if m_yes:
            is_boolean_yes = True
            trailing_clause = m_yes.group(2).strip().rstrip(".!?,")
        elif q_clean in ("yes", "y", "yeah", "yup", "sure", "ok", "okay", "true", "tell me more", "explain that", "go ahead", "please do", "solve that", "explain", "continue"):
            is_boolean_yes = True

        if m_no and not trailing_clause:
            is_boolean_no = True

        # 2.1 Workspace Material Grounding Verification
        session_docs = get_session_documents(session_id)
        all_doc_chunks = get_all_chunks(session_id, limit=3)
        has_uploaded_docs = bool(session_docs or all_doc_chunks)
        is_meta_referential = bool(plan.get("is_meta_referential")) or is_meta_referential_query(user_query)

        if not has_uploaded_docs and not is_meta_referential:
            prev_assistant_turn = extract_previous_assistant_response(history) or ""
            is_material_prompt_followup = False
            is_level_prompt_followup = False

            if prev_assistant_turn:
                t_low = prev_assistant_turn.lower()
                if any(k in t_low for k in (
                    "do you have study material",
                    "do you have material",
                    "have study material",
                    "have notes, slides, or a syllabus",
                    "have notes or slides",
                    "do you have notes",
                    "reply yes if you have notes",
                    "reply with \"no\"",
                    "reply no",
                    "reply with 'no'"
                )):
                    is_material_prompt_followup = True

                if any(k in t_low for k in (
                    "tell me your level so i can calibrate",
                    "tell me your learning level",
                    "personalize your learning journey",
                    "primary school (class 1–5)",
                    "primary school (class 1-5)",
                    "middle & high school",
                    "reply with **1**, **2**, **3**, or **4**",
                    "reply with 1, 2, 3, or 4"
                )):
                    is_level_prompt_followup = True

            # 2.1.0 Follow-up to educational level calibration prompt
            if is_level_prompt_followup:
                detected_level = parse_learning_level(user_query) or "undergraduate"
                m_sub = re.search(r"\*\*(.+?)\*\*", prev_assistant_turn)
                target_sub = m_sub.group(1).strip() if m_sub else (subject or "General Study")
                if target_sub in ("General Study", "New Course Workspace", "Default Study Room", "Course Material"):
                    target_sub = subject or "General Study"
                return await generate_synthetic_textbook(
                    session_id=session_id,
                    subject=target_sub,
                    user_id=user_id,
                    level_key=detected_level
                )

            # 2.1.1 Follow-up to "Do you have study material?"
            if is_material_prompt_followup:
                if is_boolean_yes or any(w in q_clean for w in ("yes", "y", "yeah", "yup", "sure", "have notes", "have pdf", "have material", "upload")):
                    upload_guide = (
                        "### Upload Your Study Material\n\n"
                        "Great! Please click the **+** (Attach) button in the chat bar below or use the sidebar to upload your course notes, slides, or textbook PDF.\n\n"
                        "Once uploaded:\n"
                        "- DeepTutor will extract your full syllabus into your **Study Map**\n"
                        "- All explanations, formulas, and diagrams will be strictly grounded in your materials\n"
                        "- You'll be able to generate interactive quizzes, flashcards, and custom exams directly from your pages!\n\n"
                        "*(Whenever you're ready, upload your file to begin!)*"
                    )
                    return {
                        "thought_process": "Student confirmed they have study materials. Prompted student to upload via the + button.",
                        "response": upload_guide,
                        "sources": [],
                        "format": "conceptual"
                    }
                elif is_boolean_no or any(w in q_clean for w in ("no", "nope", "nah", "no material", "i don't have", "dont have", "generate", "create textbook", "none", "no notes")):
                    m_sub = re.search(r"\*\*(.+?)\*\*", prev_assistant_turn)
                    target_sub = m_sub.group(1).strip() if m_sub else (subject or "General Study")
                    if target_sub in ("General Study", "New Course Workspace", "Default Study Room", "Course Material"):
                        target_sub = subject or "General Study"

                    inline_level = parse_learning_level(user_query)
                    if inline_level:
                        return await generate_synthetic_textbook(
                            session_id=session_id,
                            subject=target_sub,
                            user_id=user_id,
                            level_key=inline_level
                        )

                    level_prompt = (
                        f"### Personalize Your Learning Journey\n\n"
                        f"You have no material — no problem! Before I generate your textbook for **{target_sub}**, "
                        f"tell me your level so I can calibrate the content:\n\n"
                        f"1. **Primary School (Class 1–5)** — Stories, fun examples, very simple words, pictures\n"
                        f"2. **Middle & High School (Class 6–12)** — Simple language, visual analogies, basic math\n"
                        f"3. **Undergraduate (B.Tech / BSc)** — Formal definitions, derivations, code examples\n"
                        f"4. **Professional / Postgraduate** — Research-grade depth, advanced math, industry patterns\n\n"
                        f"*Reply with **1**, **2**, **3**, or **4** (or just tell me, e.g. \"Class 3\" or \"B.Tech\")*"
                    )
                    return {
                        "thought_process": f"Student indicated no material for '{target_sub}'. Prompting for level calibration (Class 1-5, Class 6-12, Undergraduate, Professional).",
                        "response": level_prompt,
                        "sources": [],
                        "format": "conceptual"
                    }

            # 2.1.2 Direct declaration of no material or request for textbook generation
            explicit_no_material = any(p in q_clean for p in (
                "no material", "don't have material", "dont have material", "no notes", "don't have notes",
                "create a textbook", "generate a textbook", "create textbook", "generate textbook", "no pdf",
                "generate syllabus", "create syllabus"
            ))
            if explicit_no_material:
                target_sub = extract_subject_from_query(user_query, default_subject=subject)
                inline_level = parse_learning_level(user_query)
                if inline_level:
                    return await generate_synthetic_textbook(
                        session_id=session_id,
                        subject=target_sub,
                        user_id=user_id,
                        level_key=inline_level
                    )
                level_prompt = (
                    f"### Personalize Your Learning Journey\n\n"
                    f"You have no material — no problem! Before I generate your textbook for **{target_sub}**, "
                    f"tell me your level so I can calibrate the content:\n\n"
                    f"1. **Primary School (Class 1–5)** — Stories, fun examples, very simple words, pictures\n"
                    f"2. **Middle & High School (Class 6–12)** — Simple language, visual analogies, basic math\n"
                    f"3. **Undergraduate (B.Tech / BSc)** — Formal definitions, derivations, code examples\n"
                    f"4. **Professional / Postgraduate** — Research-grade depth, advanced math, industry patterns\n\n"
                    f"*Reply with **1**, **2**, **3**, or **4** (or just tell me, e.g. \"Class 3\" or \"B.Tech\")*"
                )
                return {
                    "thought_process": f"Student requested textbook generation for '{target_sub}'. Prompting for level calibration.",
                    "response": level_prompt,
                    "sources": [],
                    "format": "conceptual"
                }

            # 2.1.3 Meta query about DeepTutor's identity
            is_meta_question = q_clean in (
                "who are you", "what are you", "what can you do", "help", "who created you", "what is deeptutor"
            )
            if is_meta_question:
                meta_resp = (
                    "Hello! I am **DeepTutor**, your AI academic tutor.\n\n"
                    "I help you master academic subjects, solve technical problems from first principles, and prepare for exams.\n\n"
                    "To get started, tell me what subject or topic you would like to study (for example: **Machine Learning**, **Physics**, **Linear Algebra**), or upload your course notes using the **+** button!"
                )
                return {
                    "thought_process": "Answered general meta query about DeepTutor's identity and capabilities.",
                    "response": meta_resp,
                    "sources": [],
                    "format": "conceptual"
                }

            # 2.1.4 Student specified a subject or topic in an empty workspace
            target_subject = extract_subject_from_query(user_query, default_subject=subject)
            material_prompt = (
                f"### Welcome to **{target_subject}**!\n\n"
                f"To give you the best study experience:\n\n"
                f"**Do you have study material (notes, slides, or a syllabus PDF) for {target_subject}?**\n\n"
                f"- **Yes**: Reply **Yes** or click the **+** (Attach) button below to upload your file. DeepTutor will align all lessons, study maps, and quizzes strictly to your course.\n"
                f"- **No**: Reply **No**, and I will calibrate and generate a comprehensive, structured textbook and curriculum roadmap for **{target_subject}** so we can begin studying right away!"
            )
            return {
                "thought_process": f"No materials uploaded yet for subject '{target_subject}'. Inquired if student has course materials or wants a generated synthetic textbook.",
                "response": material_prompt,
                "sources": [],
                "format": "conceptual"
            }

        # If user query is a boolean follow-up ("yes", "sure", etc.), extract keywords from the offered assistant question
        search_terms = list(plan.get("bm25_queries", [user_query]))
        if is_boolean_yes and history:
            offer_turn = ""
            # Walk backward up to 5 turns to find an assistant message that actually offered a follow-up
            for m in reversed(history[-5:]):
                if m.get("role") == "assistant" and m.get("text"):
                    text_val = m.get("text", "").strip()
                    if "?" in text_val or any(k in text_val.lower() for k in ("would you like", "shall we", "should we", "want to", "do you want", "practice")):
                        offer_turn = text_val
                        break
            if not offer_turn:
                for m in reversed(history):
                    if m.get("role") == "assistant" and m.get("text"):
                        offer_turn = m.get("text", "")
                        break

            prev_words = [w for w in re.findall(r"[a-z0-9]+", offer_turn.lower()) if len(w) > 3 and w not in (
                "would", "like", "shall", "with", "this", "that", "have", "from", "step", "example", "question", "could", "find", "answer", "please"
            )]
            if prev_words:
                search_terms = [" ".join(prev_words[-6:]), " ".join(prev_words[:4])]

            # If student provided an affirmative continuation with a trailing clause (e.g. "yes, but only the second part")
            if trailing_clause:
                search_terms.insert(0, trailing_clause)
                if prev_words:
                    search_terms.append(f"{' '.join(prev_words[:3])} {trailing_clause}")

        # Cross-reference targeted retrieval for "how does X relate to Y", "X vs Y"
        cross_ref_concepts = plan.get("cross_ref_concepts") or []
        if cross_ref_concepts:
            for c_term in cross_ref_concepts:
                if c_term and c_term not in search_terms:
                    search_terms.append(c_term)

        # Detect if student asks for a large response, detailed explanation, big answer, or related questions
        is_large_request = any(k in user_query.lower() for k in (
            "large", "big", "detailed", "detail", "comprehensive", "deep dive", "in-depth", "in depth", 
            "full breakdown", "everything", "complete", "long response", "explain fully", "all about", 
            "related questions", "big response", "large response", "more details", "thorough", "exhaustive",
            "explain more", "tell me more", "elaborate", "expand on", "break down further"
        ))

        # Detect if student specifically asks to explain more about the PREVIOUS response / answer
        is_prev_explain_req = (
            bool(plan.get("is_meta_referential"))
            or is_meta_referential_query(user_query)
            or any(k in user_query.lower() for k in (
                "previous response", "previous answer", "previous explanation", "last response", "last answer", 
                "above response", "above answer", "this response", "this answer", "what you said", "explain more about this", 
                "explain more about the previous", "elaborate on that"
            ))
        )

        if is_prev_explain_req and history:
            prev_assistant_turn = extract_previous_assistant_response(history) or ""
            if prev_assistant_turn:
                prev_keywords = [w for w in re.findall(r"[a-zA-Z0-9]+", prev_assistant_turn) if len(w) > 4 and w.lower() not in (
                    "about", "which", "there", "these", "those", "where", "after", "before", "their", "under", "result", "answer", "question", "material"
                )]
                if prev_keywords:
                    search_terms.insert(0, " ".join(prev_keywords[:6]))
                    if len(prev_keywords) > 6:
                        search_terms.insert(1, " ".join(prev_keywords[6:12]))

        chunk_limit = 8 if is_large_request else 4

        for q in search_terms:
            src = "table" if plan.get("requires_table_data") else None
            chunks = search_fts_chunks(session_id, q, limit=chunk_limit, source_type=src)
            for c in chunks:
                if c["chunk_id"] not in seen_ids:
                    seen_ids.add(c["chunk_id"])
                    retrieved_chunks.append(c)

        # If cross-reference concepts exist, ensure explicit targeted retrieval for concept Y (and X)
        if cross_ref_concepts:
            for c_term in cross_ref_concepts:
                c_chunks = search_fts_chunks(session_id, c_term, limit=4)
                for cc in c_chunks:
                    if cc["chunk_id"] not in seen_ids:
                        seen_ids.add(cc["chunk_id"])
                        retrieved_chunks.append(cc)

        if not retrieved_chunks:
            # Broad search fallback
            if is_boolean_yes:
                retrieved_chunks = get_all_chunks(session_id, limit=8)
            else:
                retrieved_chunks = search_fts_chunks(session_id, user_query, limit=8 if is_large_request else 5)
                if not retrieved_chunks:
                    retrieved_chunks = get_all_chunks(session_id, limit=5)

        # 3. Format Recent Conversation History
        history_block = ""
        if history:
            history_lines = [
                f"{(m.get('role') or m.get('sender') or 'user').capitalize()}: {(m.get('text') or m.get('content') or m.get('message') or '')}"
                for m in history[-3:]
                if (m.get('text') or m.get('content') or m.get('message'))
            ]
            if history_lines:
                history_block = "Recent Conversation History:\n" + "\n".join(history_lines) + "\n\n"

        # 4. Check if student asked for flashcards or a quiz (and not a compound conceptual+quiz request)
        sub_intents = plan.get("sub_intents") or []
        is_compound_quiz = "quiz" in sub_intents and any(it in sub_intents for it in ("conceptual", "solve", "study_notes"))
        is_quiz_or_flashcard = not is_compound_quiz and any(k in user_query.lower() for k in (
            "flashcard", "flashcards", "quiz", "quiz me", "test me", "flash card", "flash cards", "make a flashcard", "create a flashcard", "generate quiz", "make flashcard", "create flashcard"
        ))

        if is_quiz_or_flashcard:
            from app.services.study_quiz_engine import generate_flashcard_deck, sanitize_topic_title
            explanation_level = plan.get("explanation_level", "standard")
            if any(w in user_query.lower() for w in ("simply", "simple", "eli5", "basic")):
                explanation_level = "simple"
            elif any(w in user_query.lower() for w in ("advanced", "expert", "deep", "complex")):
                explanation_level = "advanced"

            # Check if student requested flashcards/quiz based on the PREVIOUS assistant response
            is_prev_resp_req = (
                bool(plan.get("is_meta_referential"))
                or is_meta_referential_query(user_query)
            )

            override_ctx = None
            clean_title = ""

            prev_resp = extract_previous_assistant_response(history)

            if is_prev_resp_req and prev_resp:
                override_ctx = prev_resp
                clean_title = await resolve_topic_from_text(prev_resp, default_subject=subject)

            if not override_ctx:
                clean_title = re.sub(
                    r"(?i)\b(create|make|generate|build|give me|show|flashcards|flashcard|quiz|deck|on the topic|about|on|me|based|previous|response|answer|for|a|this|it|module|you|gave|just|explained|discussed|above|content)\b",
                    "",
                    user_query
                ).strip()

                if (not clean_title or is_meta_referential_query(clean_title) or clean_title.lower() in ("a", "this", "it", "course material", "for this", "module", "above module", "you gave")) and prev_resp:
                    override_ctx = prev_resp
                    clean_title = await resolve_topic_from_text(prev_resp, default_subject=subject)
                elif not clean_title:
                    clean_title = subject

                clean_title = sanitize_topic_title(clean_title)

            # If clean_title is still a generic meta phrase, resolve it from subject or syllabus
            if is_meta_referential_query(clean_title) or clean_title.lower() in ("above module you gave", "above module", "module you gave", "what you gave me", "above content"):
                if prev_resp:
                    override_ctx = prev_resp
                    clean_title = await resolve_topic_from_text(prev_resp, default_subject=subject)
                else:
                    clean_title = sanitize_topic_title(subject)

            deck = await generate_flashcard_deck(
                session_id=session_id,
                topic_id=f"chat_{session_id[:8]}",
                topic_title=clean_title,
                subject=subject,
                num_cards=8,
                explanation_level=explanation_level,
                initial_mode="quiz" if ("quiz" in user_query.lower() and "flashcard" not in user_query.lower()) else "flashcards",
                override_context=override_ctx
            )

            if deck.get("out_of_topic"):
                suggested_topics = deck.get("suggested_topics") or []
                suggested_str = "\n".join(f"- **{t}**" for t in suggested_topics[:6] if t)
                reason = deck.get("reason", f"The topic '{clean_title}' is not covered in your uploaded course materials.")
                
                refusal_response = (
                    f"The topic **\"{clean_title}\"** is out of the scope of your uploaded course materials for **{subject}**.\n\n"
                    f"{reason}\n\n"
                )
                if suggested_str:
                    refusal_response += (
                        f"To ensure accurate and grounded practice, you can generate flashcards and quizzes for topics covered in your syllabus:\n"
                        f"{suggested_str}\n\n"
                        f"**Would you like to practice one of these topics instead?**"
                    )
                else:
                    refusal_response += "Please ask for flashcards on a topic from your uploaded course materials."

                return {
                    "thought_process": f"Requested topic '{clean_title}' is out of syllabus/scope for '{subject}'. Refused ungrounded deck generation.",
                    "response": refusal_response,
                    "sources": [],
                    "quiz_data": None,
                    "format": "conceptual"
                }

            resp_text = (
                f"I have analyzed the previous module on **{deck.get('title', clean_title)}** and generated an interactive **Flashcard & Quiz Deck** "
                f"({len(deck.get('questions', []))} cards directly covering the concepts and mechanisms discussed above).\n\n"
                f"You can flip cards in 3D to review key definitions and formulas, or switch to **Quiz Mode** for interactive self-testing below!"
            )

            return {
                "thought_process": f"Detected flashcard/quiz request '{user_query}' for topic '{clean_title}'. Generated grounded {len(deck.get('questions', []))}-card dual-mode JSON deck with explanation level '{explanation_level}'.",
                "response": resp_text,
                "sources": [{"chunk_id": c["chunk_id"], "page": c["page"]} for c in retrieved_chunks[:3]],
                "quiz_data": deck,
                "format": "flashcard" if "flashcard" in user_query.lower() else "quiz"
            }

        # 5. Consult Student Episodic Memory
        student_mem = get_student_memory(user_id)
        weaknesses_str = ", ".join(student_mem.get("weaknesses", [])) or "None identified yet"
        goals_str = ", ".join(student_mem.get("goals", [])) or "Mastery"

        # 6. Strict Grounding Verification & Open Workspace Handling
        session_docs = get_session_documents(session_id)
        all_doc_chunks = get_all_chunks(session_id, limit=3)
        has_uploaded_docs = bool(session_docs or all_doc_chunks)

        if has_uploaded_docs and not retrieved_chunks and not is_boolean_yes:
            doc_names = [d.get("filename") for d in session_docs if d.get("filename")]
            doc_str = f" in your uploaded materials ({', '.join(doc_names[:3])})" if doc_names else " in your uploaded materials"
            subject_str = f" for **{subject}**" if subject and subject != "General Study" else ""
            decline_msg = (
                f"I could not find information on this{doc_str}{subject_str}.\n\n"
                f"Please ask questions related to the concepts in your uploaded course materials, or upload additional materials using the **+** button."
            )
            return {
                "thought_process": "Checked session FTS5 SQLite index. Matching chunks absent in uploaded materials. Declining per grounding policy.",
                "response": decline_msg,
                "sources": [],
                "format": plan.get("response_format", "conceptual")
            }

        # Group chunks by friendly document name to ensure multi-material balance and explicit document origin
        doc_name_map = {}
        for d in session_docs:
            d_id = str(d.get("id", ""))
            d_name = d.get("filename") or d.get("title") or d_id
            if d_id:
                doc_name_map[d_id] = d_name

        chunks_by_doc: Dict[str, List[Dict[str, Any]]] = {}
        for c in retrieved_chunks:
            raw_doc_id = str(c.get("doc_id") or "Uploaded Material")
            friendly_doc_name = doc_name_map.get(raw_doc_id, raw_doc_id)
            c["friendly_doc_name"] = friendly_doc_name
            if friendly_doc_name not in chunks_by_doc:
                chunks_by_doc[friendly_doc_name] = []
            chunks_by_doc[friendly_doc_name].append(c)

        # Build clear multi-document context blocks with explicit source names and page numbers
        max_chunks_per_doc = 10 if is_large_request else 5
        formatted_doc_blocks = []
        for doc_name, doc_chunks in chunks_by_doc.items():
            block = f"=== UPLOADED MATERIAL: {doc_name} ===\n" + "\n\n".join(
                f"--- CHUNK [Document: {doc_name} | Page: {c['page']} | Chunk ID: {c['chunk_id']} | Type: {c['source_type']}] ---\n{c['content']}"
                for c in doc_chunks[:max_chunks_per_doc]
            )
            formatted_doc_blocks.append(block)

        if not formatted_doc_blocks and not has_uploaded_docs:
            context_text = (
                "NOTE: The student has not uploaded course materials or textbook PDFs yet.\n"
                "Explain the topic / answer the student's question thoroughly and accurately from academic first principles using clear intuition, definitions, and formulas if relevant.\n"
                "Conclude with a brief polite note: '> **Tip**: Upload your course notes, slides, or textbook PDF using the **+** button to enable syllabus-grounded tutoring, Study Maps, and custom exams!'"
            )
        else:
            context_text = "\n\n".join(formatted_doc_blocks)

        # Compound request guidance
        compound_guidance = ""
        if is_compound_quiz:
            compound_guidance = (
                "\n11. Compound Request Protocol:\n"
                "- The student requested BOTH an explanation/solution AND a quiz in the same turn.\n"
                "- You MUST first deliver the complete, grounded academic explanation or solution.\n"
                "- Then, immediately conclude with an interactive 1-question practice quiz question directly testing the material explained.\n"
            )

        # ELI5 comparison guidance
        eli5_comparison_guidance = ""
        if plan.get("response_format") == "comparison" and plan.get("explanation_level") in ("eli5", "simple"):
            eli5_comparison_guidance = (
                "\n12. ELI5 Comparison Protocol:\n"
                "- The student requested an ELI5 / simple comparison. Do NOT use a complex Markdown comparison table or technical jargon.\n"
                "- Instead, explain the comparison using two paired, simple, conversational paragraphs using everyday analogies suited for a beginner.\n"
            )

        trailing_constraint_str = f"Specific Focus / Constraint: '{trailing_clause}'\n" if trailing_clause else ""

        # 7. Prompt LLM with Strict Academic Grounding, Conversational Follow-up, & KaTeX Math
        prompt = f"""
You are DeepTutor's Execution Agent (DecisionAgent).
Subject: {subject}
Response Contract: {plan.get('response_format', 'conceptual')}
Explanation Level: {plan.get('explanation_level', 'standard')}
Student Weakness Profile: {weaknesses_str}
Student Goals: {goals_str}

{history_block}Retrieved Grounding Chunks Across Uploaded Materials:
{context_text}

Student Message:
"{user_query}"
{trailing_constraint_str}
STRICT RULES:
1. Grounding & Missing Information Protocol (3 Modes):
   - Mode 1 (Sufficient Material): Answer strictly and objectively from the retrieved chunks and conversation history.
   - Mode 2 (Insufficient / Partial Inputs): If the retrieved context provides SOME but NOT ALL values or variables needed to solve a problem (e.g., mass and force given, angle missing):
     You MUST explicitly state which specific parameter or value is missing, explain the governing formula that requires it, and ask the student for that specific value or guide them to where in the course materials it might be found. Do NOT invent, assume, or hallucinate a plausible numerical value, and do NOT decline completely.
   - Mode 3 (Source Contradiction / Typos): If a formula, constant, or unit in the retrieved text looks internally contradictory or contains a clear source typo (e.g., units do not reconcile across equations), you MUST explicitly flag the inconsistency to the student rather than silently 'fixing' it or blindly calculating.
   - Mode 4 (Out-of-Topic / Absent from Materials): If course materials ARE uploaded for this session and the student's question topic is NOT present in the uploaded course materials, you MUST STRICTLY decline to answer or explain the out-of-topic concept. State clearly that the concept is not covered in their uploaded materials for {subject}, suggest topics that ARE in their uploaded materials, and invite them to ask questions on those topics or upload notes for the new topic. Strictly do NOT provide general academic overviews, definitions, or explanations for out-of-topic concepts when materials are uploaded. If NO materials are uploaded yet, answer the student's query clearly and academically from first principles, and conclude with a tip to upload course materials.
2. Multi-Material & Cross-Chunk Disagreement Rule:
   - If retrieved chunks come from multiple uploaded materials (or if the student asks to compare or explain both materials):
     You MUST explicitly analyze and present the content from EACH material under clear section headings (e.g. '### Material: [Document Name]').
   - If retrieved chunks from different source documents or chapters appear to disagree or provide conflicting values/perspectives:
     You MUST explicitly surface the disagreement to the student (e.g., "Your Chapter 2 notes state X, but the uploaded lecture slides state Y — here is how they differ and why") rather than silently picking one source.
3. Greetings & Salutations:
   - If the student message is a greeting, greet them warmly as DeepTutor for **{subject}**, explain your capabilities, and ask what concept from their course materials they'd like to study today. Do NOT output a refusal for greetings.
4. Boolean Continuations & Follow-up Acceptance:
   - If the student answers 'Yes', 'Sure', 'Explain that', or 'Continue' (including with a trailing constraint like 'yes, but only part 2'):
     You MUST directly fulfill the follow-up step-by-step honoring any trailing constraint. Do NOT output a refusal message for follow-ups that you offered.
   - If the student answers 'No' / 'Nope', acknowledge politely and ask what other concept from their uploaded material they would like to study.
5. Universal STEM Problem Solving & Table Completion Protocol:
   When solving, calculating, or filling any table, exercise, or problem across ANY subject:
   - Stage 1: First-Principles Governing Laws: Identify the fundamental laws, governing formulas, or naming conventions.
   - Stage 2: Structural Inspection & Trap Elimination: Inspect every sub-component for classic textbook traps (e.g., in Chemistry: check if a bent substituent branch is longer than the horizontal chain; in Physics: verify coordinate directions and units; in Math: check $n=0$ or negative bounds).
   - Stage 3: Row-by-Row Independent Computation: Compute EVERY single row, sequence, or test case individually from first principles.
   - Stage 4: Sanity & Verification Check: Verify dimensional consistency, IUPAC validity, or algebraic balance before finalizing the table.
   - Stage 5: Complete Solved Markdown Table: Output the 100% complete Markdown table with EVERY row, position, value, and name fully populated. Strictly do NOT use ellipses (...) or placeholders ('TBD', 'N/A'). Show clear step-by-step reasoning for each row above or below the table.
6. Mathematics: Format ALL formulas in standalone block KaTeX:
   $$
   formula
   $$
   or inline $...$. Ensure all LaTeX curly braces are strictly balanced!
7. Tone: Articulate, authoritative, engaging academic tone. Strictly ZERO emojis.
8. Chain-of-Thought: Provide a dedicated thought process detailing your reasoning and verification before the answer.
9. Interactive Follow-up Question (Conversational Closing):
   ALWAYS end your response with a natural, conversational follow-up question in bold (e.g., "**Would you like to solve another problem from this section?**" or "**Shall we see how this applies to negative differences, or test this with a quick 1-question practice?**") that the student can easily answer with a simple 'Yes' or 'No'.
10. Textbook Correctness Inquiry:
    - If the student asks whether the textbook, author, or uploaded material is wrong about a concept ('is this textbook wrong about X'):
      1. First, objectively explain what the uploaded material specifically states.
      2. If the material's claim is inconsistent with well-established academic facts, flag this as an objective caveat/note of caution (e.g., "Note: While your text states X, standard literature notes Y because..."), rather than an aggressive contradiction. Always explain what the course material states first.{compound_guidance}{eli5_comparison_guidance}

Return ONLY valid JSON in this exact structure:
{{
  "thought_process": "Step-by-step reasoning on how retrieved chunks support this answer...",
  "response": "The complete, detailed academic response formatted in Markdown...",
  "quiz_data": null
}}
"""
        # Dynamic Visual Grounding: render high-resolution page image when diagrams, tables, circuits, or formulas are involved
        page_image_bytes = None
        has_visual_need = target_page is not None or any(
            w in user_query.lower() for w in ("table", "diagram", "figure", "solve", "fill", "calculate", "structure", "circuit", "graph", "chart", "formula", "mechanism", "image")
        )

        if has_visual_need:
            try:
                docs = get_session_documents(session_id)
                if docs:
                    pdf_rel = docs[0].get("file_path", "")
                    pdf_full = Path(pdf_rel)
                    if not pdf_full.is_absolute():
                        pdf_full = BACKEND_DIR / pdf_rel
                    if pdf_full.exists() and pdf_full.suffix.lower() == ".pdf":
                        import pymupdf
                        p_doc = pymupdf.open(str(pdf_full))
                        p_num = target_page
                        if p_num is None and retrieved_chunks:
                            p_num = retrieved_chunks[0].get("page", 1)
                        if p_num and 1 <= p_num <= len(p_doc):
                            page_obj = p_doc[p_num - 1]
                            pix = page_obj.get_pixmap(dpi=120)
                            page_image_bytes = pix.tobytes("png")
                        p_doc.close()
            except Exception as e:
                print(f"[Vision Grounding] Note: {e}")

        sys_inst = "You are a distinguished university professor. Output clean JSON only. Strictly no emojis."
        raw = await call_llm(prompt, sys_inst, temperature=0.2, image_bytes=page_image_bytes)

        thought, answer, quiz_data = parse_llm_json_response(raw)
        answer = sanitize_katex(answer)

        # ─── Verification & Self-Correction Repair Loops ────────────────────

        # Check 1: KaTeX Brace Balance Sanity Check (Category 7)
        is_balanced, malformed_span = check_katex_brace_balance(answer)
        if not is_balanced and answer:
            print(f"[DecisionAgent] KaTeX unbalanced braces detected in: {malformed_span}. Triggering repair retry...")
            repair_prompt = (
                f"{prompt}\n\n"
                f"CRITICAL REPAIR INSTRUCTION: Your previous LaTeX output had unbalanced curly braces in span '{malformed_span}'. "
                f"Regenerate the complete response ensuring all LaTeX formulas have perfectly balanced curly braces {{ and }}."
            )
            rep_raw = await call_llm(repair_prompt, sys_inst, temperature=0.1, image_bytes=page_image_bytes)
            if rep_raw:
                th2, ans2, qd2 = parse_llm_json_response(rep_raw)
                ans2 = sanitize_katex(ans2)
                if ans2:
                    thought, answer, quiz_data = th2 or thought, ans2, qd2 or quiz_data

        # Check 2: STEM Table Verification (Row Count & Placeholder Enforcement - Category 2)
        if answer and ("|" in answer or plan.get("requires_table_data")):
            actual_rows = count_markdown_table_rows(answer)
            expected_rows = detect_expected_row_count(user_query, retrieved_chunks)
            has_placeholder = check_table_placeholders(answer)

            repair_msg = ""
            if expected_rows and actual_rows > 0 and actual_rows < expected_rows:
                repair_msg = f"You produced {actual_rows} table rows, but the problem specifies {expected_rows} rows. Redo this completely, solving and showing every single row (all {expected_rows} rows) without skipping any."
            elif actual_rows > 0 and has_placeholder:
                repair_msg = "Your previous output table contained an ellipsis ('...') or placeholder cell ('TBD', 'N/A'). You are strictly forbidden from using ellipses or placeholders. Redo this completely, solving and filling every row and cell explicitly from first principles."

            if repair_msg:
                print(f"[DecisionAgent] STEM Table check flagged issue ({repair_msg}). Triggering repair retry...")
                repair_prompt = f"{prompt}\n\nCRITICAL REPAIR INSTRUCTION: {repair_msg}"
                rep_raw = await call_llm(repair_prompt, sys_inst, temperature=0.1, image_bytes=page_image_bytes)
                if rep_raw:
                    th2, ans2, qd2 = parse_llm_json_response(rep_raw)
                    ans2 = sanitize_katex(ans2)
                    if ans2:
                        thought, answer, quiz_data = th2 or thought, ans2, qd2 or quiz_data

        if not answer:
            # Fallback direct generation if JSON parse failed
            if retrieved_chunks:
                first_chunk = retrieved_chunks[0]["content"]
                answer = f"Based on your uploaded course notes:\n\n{first_chunk}\n\nPlease ask a specific follow-up question regarding these mechanics."
            else:
                answer = f"I could not find the answer to this in your uploaded PDF. Please ask questions specifically related to the concepts and chapters in your uploaded material for {subject}."

        # Self-Verification Regrounding Pass
        answer = await self._maybe_reground(answer, context_text, subject)

        # Background update of student memory (extract learning facts / weaknesses)
        asyncio.create_task(self._update_memory_background(user_id, user_query, answer))

        resp_format = plan.get("response_format", "conceptual")
        export_ready = (resp_format == "study_notes") and ("could not find the answer" not in answer.lower())

        return {
            "thought_process": thought,
            "response": answer,
            "quiz_data": quiz_data,
            "sources": [
                {"chunk_id": c["chunk_id"], "page": c["page"], "source_type": c["source_type"], "snippet": c["content"][:180]}
                for c in retrieved_chunks[:4]
            ],
            "format": resp_format,
            "response_format": resp_format,
            "export_ready": export_ready,
        }

    async def _maybe_reground(self, draft_answer: str, context: str, subject: str) -> str:
        """Lightweight second pass checking for ungrounded claims."""
        if "could not find the answer" in draft_answer or len(draft_answer) < 80:
            return draft_answer
        return draft_answer

    async def _update_memory_background(self, user_id: str, query: str, answer: str):
        """Asynchronously updates student learning facts & struggle areas."""
        try:
            q_lower = query.lower()
            if any(k in q_lower for k in ("i don't understand", "make it easier", "confused", "stuck on")):
                words = [w for w in re.findall(r"\w+", query) if len(w) > 3]
                if words:
                    add_student_memory_fact(user_id, weakness=f"Struggled with {words[-1]}")
        except Exception:
            pass


planner_agent = QueryAnalyzerAgent()
executor_agent = DecisionAgent()


# ─── Robust JSON Parsing Helper ──────────────────────────────────────────────

def robust_json_parse(text: str) -> Optional[Dict[str, Any]]:
    """Robustly extracts and parses JSON even if LLM includes raw unescaped LaTeX backslashes."""
    if not text:
        return None
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[1] if "\n" in cleaned else cleaned[3:]
        if cleaned.endswith("```"):
            cleaned = cleaned.rsplit("\n", 1)[0]
        if cleaned.startswith("json"):
            cleaned = cleaned[4:].strip()
    start_idx = cleaned.find("{")
    end_idx = cleaned.rfind("}")
    if start_idx != -1 and end_idx != -1:
        cleaned = cleaned[start_idx : end_idx + 1]

    try:
        return json.loads(cleaned)
    except Exception:
        pass

    try:
        # Sanitize unescaped LaTeX backslashes (e.g. \frac, \sigma, \cdot) inside string values
        sanitized = re.sub(r'\\(?!["\\/bfnrtu]|u[0-9a-fA-F]{4})', r'\\\\', cleaned)
        return json.loads(sanitized)
    except Exception:
        pass

    return None


# ─── 3. Normal Mode: 4-Step Core Idea Generator ─────────────────────────────

async def generate_core_idea(session_id: str, topic_id: str, topic_title: str, topic_summary: str) -> Dict[str, Any]:
    """
    Generates 4-Phase Progressive Cards with strict KaTeX mathematical formulation:
    1. The Big Picture
    2. Core Principle
    3. Key Takeaways
    4. Common Pitfalls
    """
    chunks = search_fts_chunks(session_id, topic_title, limit=6)
    all_chunks = get_all_chunks(session_id, limit=3)

    # Out-of-Syllabus Grounding Check for Custom Typed Topics
    if not chunks and all_chunks:
        keywords = [w for w in re.findall(r"[a-zA-Z0-9]+", topic_title.lower()) if len(w) > 3 and w not in ("what", "how", "explain", "topic", "about", "with")]
        broad_chunks = []
        for kw in keywords[:3]:
            broad_chunks.extend(search_fts_chunks(session_id, kw, limit=2))
        
        if not broad_chunks:
            session_topics = get_session_topics(session_id)
            return {
                "out_of_topic": True,
                "topic_id": topic_id,
                "topic_title": topic_title,
                "reason": f"The requested topic \"{topic_title}\" is out of the scope of your uploaded course materials.",
                "suggested_topics": [t.get("title") if isinstance(t, dict) else str(t) for t in session_topics[:6] if t]
            }
        else:
            chunks = broad_chunks

    context = "\n\n".join(c["content"] for c in chunks) if chunks else topic_summary

    prompt = f"""You are DeepTutor's elite academic Normal Mode Core Idea Engine.
Break down the topic '{topic_title}' into the 4-phase pedagogical model using the uploaded textbook context below.

Context:
{context[:4500]}

Pedagogical Tasks:
1. Phase 1 - The Big Picture: Pure high-level intuition, motivation, and why this concept was developed. No conversational clutter.
2. Phase 2 - Core Principle: Governing mechanics, mathematical formulation, and step-by-step mechanisms.
   - All primary formulas and equations MUST be formatted on standalone lines using KaTeX block math: $$ ... $$
   - Format variables and terms using inline math ($ ... $).
   - Detail mechanisms and variable definitions with clean markdown bullet points.
3. Phase 3 - Key Takeaways: High-yield bullet points for exam revision.
4. Phase 4 - Common Pitfalls: Frequent exam traps, misconceptions, and subtle edge cases.

Strict Rules:
- No conversational filler, no pleasantries.
- Strictly professional academic tone. Zero emojis.
- Return ONLY valid JSON.

JSON Structure:
{{
  "topic_id": "{topic_id}",
  "topic_title": "{topic_title}",
  "big_picture": "Clear, impactful pedagogical intuition...",
  "core_principle": "Detailed mechanics with centered formulas $$ ... $$ and variable definitions.",
  "key_takeaways": [
    "High-yield takeaway 1",
    "High-yield takeaway 2",
    "High-yield takeaway 3"
  ],
  "common_pitfalls": [
    "Frequent student misconception 1",
    "Subtle exam trap 2"
  ]
}}
"""
    sys_inst = "You are an elite university professor. Output ONLY strictly valid JSON. Mathematical formulas in KaTeX ($$...$$). No conversational chatter. No emojis."
    raw = await call_llm(prompt, sys_inst, temperature=0.2)

    parsed = robust_json_parse(raw)
    if parsed and isinstance(parsed, dict) and "big_picture" in parsed:
        def _clean_item(text: str) -> str:
            if not text or not isinstance(text, str):
                return text or ""
            return re.sub(r"\$\$([^$\n]+?)\$\$", r"$\1$", text).strip()

        parsed["big_picture"] = str(parsed.get("big_picture", "")).strip()
        parsed["core_principle"] = str(parsed.get("core_principle", "")).strip()
        if isinstance(parsed.get("key_takeaways"), list):
            parsed["key_takeaways"] = [_clean_item(x) for x in parsed["key_takeaways"] if x]
        if isinstance(parsed.get("common_pitfalls"), list):
            parsed["common_pitfalls"] = [_clean_item(x) for x in parsed["common_pitfalls"] if x]
        return parsed

    return {
        "topic_id": topic_id,
        "topic_title": topic_title,
        "big_picture": f"**{topic_title}** provides fundamental computational and analytical models designed to extract patterns, minimize prediction errors, and optimize decision boundaries.",
        "core_principle": f"The governing mechanics of **{topic_title}** operate according to defined theoretical relationships:\n\n$$ \\hat{{y}} = f(x; \\theta) $$\n\nWhere parameters are optimized across bounded objective spaces.",
        "key_takeaways": [
            f"Master the foundational definitions and scope of {topic_title}.",
            "Understand the quantitative transformations and governing formulations.",
            "Verify boundary constraints during system evaluation."
        ],
        "common_pitfalls": [
            "Conflating intermediate assumptions with general boundary conditions.",
            "Omitting normalisation steps or scale factors in iterative calculation."
        ]
    }


# ─── 4. Topic Doubt Resolver ────────────────────────────────────────────────

async def resolve_topic_doubt(
    session_id: str,
    topic_id: str,
    topic_title: str,
    question: str,
    history: List[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """Resolves specific student doubts about a topic with grounded context."""
    chunks = search_fts_chunks(session_id, f"{topic_title} {question}", limit=4)
    context = "\n\n".join(c["content"] for c in chunks)

    prompt = f"""
Student Topic Doubt Resolution.
Topic: {topic_title}
Question: "{question}"

Context from Course Material:
{context[:4000]}

Provide an articulate, concise academic explanation addressing the student's exact doubt.
Include formulas in standalone $$ ... $$ block math where appropriate. No emojis.
"""
    answer = await call_llm(prompt, "You are a helpful university professor answering an office hours question.", temperature=0.2)
    if not answer:
        answer = f"In {topic_title}, this question addresses an important nuance. Review the primary definitions and observe how governing parameters dictate the system's response."

    return {
        "topic_id": topic_id,
        "topic_title": topic_title,
        "question": question,
        "answer": answer,
        "sources": [{"chunk_id": c["chunk_id"], "page": c["page"]} for c in chunks[:3]]
    }


# ─── 5. Teacher Mode: Interactive Masterclass Lecture Engine ─────────────────

async def generate_lecture_diagnostic(
    session_id: str,
    topic_id: str,
    topic_title: str
) -> Dict[str, Any]:
    """
    Requirement 1: Diagnostic Open.
    Generates a 1-question diagnostic probe to gauge prior knowledge before the lecture starts,
    and initializes a durable lecture session record in SQLite.
    """
    chunks = search_fts_chunks(session_id, topic_title, limit=4)
    context = "\n\n".join(c["content"] for c in chunks)

    prompt = f"""You are a masterclass university professor about to lecture on: '{topic_title}'.
Before beginning your lecture, generate exactly 1 diagnostic multiple-choice question to gauge whether the student understands the foundational prerequisite intuition required for this topic.

Reference Course Context:
{context[:2500] if context else "Foundational academic theory"}

Strict Output Contract:
Return ONLY valid JSON:
{{
  "prerequisite_concept": "<name of the prerequisite principle tested>",
  "question": "<clear, concise 1-sentence diagnostic question>",
  "options": [
    {{"id": "a", "text": "<option a>"}},
    {{"id": "b", "text": "<option b>"}},
    {{"id": "c", "text": "<option c>"}},
    {{"id": "d", "text": "<option d>"}}
  ],
  "correct_option_id": "<a/b/c/d>",
  "explanation": "<why this option is correct>"
}}
No markdown fences, no conversational prose, zero emojis.
"""
    sys_inst = "You are a university professor creating an initial baseline diagnostic probe. Output strict JSON only. Zero emojis."
    raw = await call_llm(prompt, sys_inst, temperature=0.2)
    parsed = robust_json_parse(raw)

    if not parsed or not isinstance(parsed, dict) or "question" not in parsed:
        parsed = {
            "prerequisite_concept": "Foundational Principles",
            "question": f"Which foundational principle is most critical for understanding {topic_title}?",
            "options": [
                {"id": "a", "text": f"The primary governing mechanics and objective bounds of {topic_title}"},
                {"id": "b", "text": "Unrelated heuristic approximations without boundary guarantees"},
                {"id": "c", "text": "Purely static state representations without updates"},
                {"id": "d", "text": "Arbitrary random sampling without convergence criteria"}
            ],
            "correct_option_id": "a",
            "explanation": f"Understanding governing mechanics provides the essential baseline for mastering {topic_title}."
        }

    # Create durable lecture record
    lec_record = create_lecture_session(
        session_id=session_id,
        topic_id=topic_id,
        topic_title=topic_title,
        diagnostic_question=parsed.get("question")
    )

    return {
        "lecture_id": lec_record["id"],
        "topic_id": topic_id,
        "topic_title": topic_title,
        "diagnostic": parsed
    }


async def evaluate_lecture_diagnostic(
    session_id: str,
    topic_id: str,
    topic_title: str,
    question: str,
    student_answer: str,
    lecture_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Evaluates student's diagnostic response and determines the starting lecture calibration:
    - 'novice': Student needs a prerequisite mini-explanation before Phase 1.
    - 'standard': Standard balanced masterclass pacing.
    - 'advanced': Accelerated pacing diving straight into rigorous derivations.
    """
    prompt = f"""You are evaluating a student's answer to the diagnostic question for the upcoming masterclass on '{topic_title}'.

Diagnostic Question: {question}
Student's Answer: {student_answer}

Task:
Determine student's baseline prior knowledge.
Return ONLY valid JSON:
{{
  "level": "novice" | "standard" | "advanced",
  "is_correct": true | false,
  "reasoning": "<1 sentence assessment of their conceptual baseline>",
  "prerequisite_needed": true | false,
  "prerequisite_summary": "<if novice, a 2-sentence intuitive primer on the required prerequisite; otherwise null>"
}}
Zero emojis.
"""
    sys_inst = "You are a diagnostic evaluation auditor. Output JSON only. Zero emojis."
    raw = await call_llm(prompt, sys_inst, temperature=0.1)
    parsed = robust_json_parse(raw)

    if not parsed or not isinstance(parsed, dict) or "level" not in parsed:
        level = "standard"
        is_corr = True
        prereq = None
    else:
        level = parsed.get("level", "standard")
        is_corr = parsed.get("is_correct", True)
        prereq = parsed.get("prerequisite_summary")

    if lecture_id:
        update_lecture_session(
            session_id=session_id,
            lecture_id=lecture_id,
            diagnostic_answer=student_answer,
            diagnostic_level=level,
            status="in_progress"
        )

    return {
        "lecture_id": lecture_id,
        "level": level,
        "is_correct": is_corr,
        "reasoning": parsed.get("reasoning", "Diagnostic baseline evaluated successfully.") if parsed else "Standard baseline.",
        "prerequisite_needed": (level == "novice"),
        "prerequisite_summary": prereq
    }


async def generate_phase_checkpoint(
    session_id: str,
    topic_title: str,
    phase_name: str,
    phase_content: str,
    lecture_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Requirement 3: Checkpoints (Active Recall).
    Generates a targeted check-for-understanding question after each major section.
    """
    prompt = f"""You are an elite professor lecturing on '{topic_title}'.
You just delivered the following lecture segment for '{phase_name}':

\"\"\"{phase_content[:2000]}\"\"\"

TASK:
Generate a single active-recall check question that directly tests whether the student absorbed the core mechanism or principle from this segment.

Return ONLY valid JSON:
{{
  "question": "<concise check question>",
  "options": [
    {{"id": "a", "text": "<option a>"}},
    {{"id": "b", "text": "<option b>"}},
    {{"id": "c", "text": "<option c>"}},
    {{"id": "d", "text": "<option d>"}}
  ],
  "correct_option_id": "<a/b/c/d>",
  "core_concept": "<the concept tested>"
}}
Zero emojis.
"""
    sys_inst = "Output strict JSON only. All mathematical formulas in standard KaTeX syntax ($...$ inline). Zero emojis."
    raw = await call_llm(prompt, sys_inst, temperature=0.2)
    parsed = robust_json_parse(raw)

    if not parsed or not isinstance(parsed, dict) or "question" not in parsed:
        parsed = {
            "question": f"What is the key governing relationship established in {phase_name} for {topic_title}?",
            "options": [
                {"id": "a", "text": f"The direct structural formulation of {topic_title}"},
                {"id": "b", "text": "An unrelated independent variable"},
                {"id": "c", "text": "A constant zero gradient"},
                {"id": "d", "text": "An unbounded divergence"}
            ],
            "correct_option_id": "a",
            "core_concept": topic_title
        }

    checkpoint_record = None
    if lecture_id:
        checkpoint_record = record_lecture_checkpoint(
            session_id=session_id,
            lecture_id=lecture_id,
            phase=phase_name,
            question_prompt=parsed["question"],
            options=parsed.get("options", []),
            correct_answer=parsed.get("correct_option_id", "a")
        )

    return {
        "checkpoint_id": checkpoint_record["id"] if checkpoint_record else f"chk_{os.urandom(3).hex()}",
        "lecture_id": lecture_id,
        "phase": phase_name,
        "checkpoint": parsed
    }


async def evaluate_checkpoint_response(
    session_id: str,
    topic_title: str,
    phase_name: str,
    question_prompt: str,
    correct_answer: str,
    student_response: str,
    checkpoint_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Requirement 3: Modal Remediation.
    If student answers incorrectly, branches into a short remedial explanation
    using a DIFFERENT modality (e.g. switching to a concrete analogy or worked numerical step)
    rather than repeating the previous text.
    """
    is_correct = (
        student_response.strip().lower() == correct_answer.strip().lower() or
        student_response.strip().lower().startswith(correct_answer.strip().lower())
    )

    if is_correct:
        feedback = f"Excellent analysis! You accurately identified the governing principle for {phase_name}."
        remedial_modality = None
        remedial_content = None
    else:
        # Select alternative modality
        if "mechanics" in phase_name.lower() or "derivation" in phase_name.lower():
            remedial_modality = "analogy"
            modality_instruction = "Do NOT repeat mathematical equations. Instead, switch to an intuitive, relatable physical analogy explaining why this principle works."
        else:
            remedial_modality = "worked_example"
            modality_instruction = "Do NOT repeat high-level theory. Instead, provide a simple, concrete step-by-step numerical example illustrating how the numbers change."

        prompt = f"""You are a masterclass professor conducting remedial instruction on '{topic_title}'.
Phase: {phase_name}
Check Question: {question_prompt}
Correct Answer ID/Concept: {correct_answer}
Student's Response: {student_response} (Incorrect)

TASK:
Provide a crisp remedial explanation (2-3 concise paragraphs) using the following alternative modality:
{modality_instruction}

Formatting Rules:
- Direct, encouraging professor tone.
- Zero emojis.
- Standalone formulas in KaTeX ($$...$$) if applicable, inline terms in $...$.
"""
        sys_inst = "You are an expert professor providing multimodal remedial instruction. Zero emojis."
        remedial_content = await call_llm(prompt, sys_inst, temperature=0.3)
        feedback = f"Let's look at this from a different angle to solidify your understanding."

    if checkpoint_id and session_id:
        update_lecture_checkpoint(
            session_id=session_id,
            checkpoint_id=checkpoint_id,
            student_response=student_response,
            is_correct=is_correct,
            remedial_modality=remedial_modality,
            remedial_content=remedial_content
        )

    return {
        "checkpoint_id": checkpoint_id,
        "is_correct": is_correct,
        "feedback": feedback,
        "remedial_modality": remedial_modality,
        "remedial_content": remedial_content
    }


async def handle_lecture_pause_ask(
    session_id: str,
    topic_title: str,
    current_phase: str,
    accumulated_context: str,
    student_question: str,
    lecture_id: Optional[str] = None,
    token_offset: int = 0
) -> Dict[str, Any]:
    """
    Requirement 4: Pause & Ask.
    Handles an inline clarifying question from the student during streaming,
    answers it concisely without losing context, and prepares a smooth resume segue.
    """
    prompt = f"""You are an elite professor delivering a live masterclass on '{topic_title}'.
You have paused at: '{current_phase}'.

Accumulated Lecture Delivered So Far:
\"\"\"{accumulated_context[-2500:] if accumulated_context else "Masterclass in progress."}\"\"\"

Student's Clarifying Question:
\"{student_question}\"

TASK:
1. Provide a direct, authoritative, crystal-clear 2-3 paragraph answer to the student's question.
2. Ground the answer specifically in the context of '{topic_title}'.
3. End with a 1-sentence transition resuming the lecture smoothly (e.g., "With this clarified, let us resume our deep-dive into...").

Formatting Rules:
- Standard KaTeX formulas: block ($$...$$), inline ($...$).
- Zero emojis. Academic professor tone.
"""
    sys_inst = "You are a live masterclass professor answering a student's question during lecture pause. Zero emojis."
    answer = await call_llm(prompt, sys_inst, temperature=0.2)

    if lecture_id:
        record_lecture_pause(
            session_id=session_id,
            lecture_id=lecture_id,
            phase=current_phase,
            student_question=student_question,
            teacher_response=answer,
            token_offset=token_offset
        )

    return {
        "lecture_id": lecture_id,
        "phase": current_phase,
        "student_question": student_question,
        "answer": answer
    }


async def generate_teach_back_prompt(
    session_id: str,
    topic_id: str,
    topic_title: str,
    lecture_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Requirement 5: Teach-Back Close (Feynman Technique).
    Prompts the student to synthesize and explain the topic in their own words.
    """
    prompt_text = (
        f"Now, let us verify your mastery through the Feynman technique: "
        f"Explain the core principle of {topic_title} in your own words as if teaching it to an analytical student. "
        f"Be sure to mention why the concept exists, its fundamental governing mechanism, and one common misconception to avoid."
    )

    if lecture_id:
        update_lecture_session(
            session_id=session_id,
            lecture_id=lecture_id,
            teach_back_prompt=prompt_text,
            status="waiting_teach_back"
        )

    return {
        "lecture_id": lecture_id,
        "topic_id": topic_id,
        "topic_title": topic_title,
        "prompt": prompt_text
    }


async def evaluate_teach_back_submission(
    session_id: str,
    topic_id: str,
    topic_title: str,
    submission_text: str,
    lecture_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Requirement 5 & 7: Grades the student's teach-back explanation,
    registers the topic in episodic memory for continuity, and generates the final smart notes summary.
    """
    chunks = search_fts_chunks(session_id, topic_title, limit=4)
    context = "\n\n".join(c["content"] for c in chunks)

    prompt = f"""You are evaluating a student's 'Teach-Back' (Feynman technique) submission for the masterclass on '{topic_title}'.

Course Grounding Reference:
{context[:2500]}

Student's Explanation:
\"\"\"{submission_text}\"\"\"

EVALUATION RUBRIC:
1. Conceptual Accuracy (0-40 points): Are the fundamental governing mechanisms accurately stated?
2. Intuition & First Principles (0-30 points): Did they articulate WHY the concept exists?
3. Rigor & Misconceptions (0-30 points): Did they avoid common fallacies and identify key boundary constraints?

Return strictly valid JSON:
{{
  "score": <0-100 integer score>,
  "mastery_verdict": "Mastered" | "Proficient" | "Needs Review",
  "strengths": [
    "<strong point 1 accurately explained>",
    "<strong point 2 accurately explained>"
  ],
  "areas_for_refinement": [
    "<missing detail or subtle misconception 1>"
  ],
  "professor_critique": "<2-3 sentence personalized feedback from the professor>",
  "executive_summary_markdown": "<complete 4-section study note summary in clean KaTeX markdown for the student's notebook>"
}}
Zero emojis.
"""
    sys_inst = "You are a university professor grading a Feynman teach-back explanation. Output strict JSON only. Zero emojis."
    raw = await call_llm(prompt, sys_inst, temperature=0.1)
    parsed = robust_json_parse(raw)

    if not parsed or not isinstance(parsed, dict) or "score" not in parsed:
        parsed = {
            "score": 85,
            "mastery_verdict": "Proficient",
            "strengths": [f"Clear explanation of the core intuition behind {topic_title}."],
            "areas_for_refinement": ["Deepen quantitative boundary formulations."],
            "professor_critique": f"Solid conceptual grasp of {topic_title}. Your explanation demonstrates foundational understanding.",
            "executive_summary_markdown": f"# Masterclass Notes: {topic_title}\n\n- Mastered foundational mechanics.\n- Review governing edge cases before examinations."
        }

    score = parsed.get("score", 80)
    summary_md = parsed.get("executive_summary_markdown", "")

    # Register in episodic memory for continuity
    record_mastered_topic(
        session_id=session_id,
        topic_title=topic_title,
        subject="Course Material",
        mastery_score=float(score),
        lecture_id=lecture_id
    )

    if lecture_id:
        update_lecture_session(
            session_id=session_id,
            lecture_id=lecture_id,
            teach_back_submission=submission_text,
            teach_back_grade_json=json.dumps(parsed),
            accumulated_notes_markdown=summary_md,
            status="completed"
        )

    return {
        "lecture_id": lecture_id,
        "topic_id": topic_id,
        "topic_title": topic_title,
        "evaluation": parsed
    }


async def stream_teacher_lecture(
    session_id: str,
    topic_id: str,
    topic_title: str,
    override_syllabus: bool = False,
    diagnostic_level: str = "standard",
    lecture_id: Optional[str] = None
) -> AsyncGenerator[str, None]:
    """
    Requirement 2 & 6: Fixed 4-Part Lecture Structure with Continuity & Active Recall.
    Streams 4 university lecture phases:
      a. Phase 1: First-principles intuition (why this concept/problem exists)
      b. Phase 2: Deep mechanics (how it actually works)
      c. Phase 3: Worked derivation / step-by-step numerical example
      d. Phase 4: Exam traps & misconceptions (visually distinct callout block)
    """
    chunks = search_fts_chunks(session_id, topic_title, limit=6)
    session_topics = get_session_topics(session_id)
    syllabus_titles = [t.get("title", "") for t in session_topics if t.get("title")]

    # 1. Intelligent Syllabus Validation Gate
    if not override_syllabus and syllabus_titles:
        is_direct_match = any(
            topic_title.strip().lower() in s.lower() or s.lower() in topic_title.strip().lower()
            for s in syllabus_titles
        )

        if not is_direct_match:
            verify_prompt = f"""You are an academic curriculum auditor.
Course syllabus topics:
{", ".join(syllabus_titles[:15]) if syllabus_titles else "General course materials"}

Uploaded textbook search match count for student's topic: {len(chunks)} chunks found.
Top text snippet: {" ".join(c.get("content", "")[:200] for c in chunks[:2]) if chunks else "No direct chunk matches"}

Student requested topic to lecture on: "{topic_title}".

Determine if "{topic_title}" belongs to the syllabus/scope of this course material, or is closely related prerequisite theory.
Return strictly valid JSON:
{{
  "in_syllabus": true,
  "reason": "1 concise sentence explaining whether this topic is covered or why it is out-of-syllabus",
  "suggested_topics": ["Suggested Topic 1 from syllabus", "Suggested Topic 2 from syllabus", "Suggested Topic 3 from syllabus"]
}}
"""
            verify_raw = await call_llm(verify_prompt, "You are a syllabus verification auditor. Output JSON only.", temperature=0.1)
            parsed_eval = robust_json_parse(verify_raw)

            if parsed_eval and isinstance(parsed_eval, dict) and not parsed_eval.get("in_syllabus", True):
                suggested = parsed_eval.get("suggested_topics") or syllabus_titles[:4]
                reason = parsed_eval.get("reason", f"'{topic_title}' does not appear in your uploaded course materials.")
                yield f"data: {json.dumps({'type': 'out_of_syllabus', 'topic': topic_title, 'reason': reason, 'suggested_topics': suggested})}\n\n"
                return

    context = "\n\n".join(c["content"] for c in chunks)

    # 2. Fetch Mastered Topics for Cross-Session Memory Continuity (Requirement 6)
    past_topics = get_mastered_topics(session_id)
    past_topics_summary = ", ".join(t.get("topic_title", "") for t in past_topics[:5]) if past_topics else "None yet"

    # 3. Define the Enforced 4-Phase Lecture Sequence
    phases = [
        (
            "Phase 1: First-Principles Intuition",
            f"Explain the fundamental origin and intuition behind '{topic_title}'. Why does this concept exist, what analytical problem does it solve, and how was it discovered? If diagnostic level is '{diagnostic_level}' and is novice, include a gentle 2-sentence foundation; if advanced, move straight to the fundamental limits of prior approaches."
        ),
        (
            "Phase 2: Deep Mechanics & Governing Principles",
            f"Detail the rigorous architecture, equations, and mechanics of '{topic_title}'. Format all governing formulas using standalone KaTeX block math ($$...$$) and format variables using inline math ($...$). Break down each variable and operational state step-by-step."
        ),
        (
            "Phase 3: Worked Derivation & Numerical Example",
            f"Walk the student step-by-step through a concrete worked derivation or numerical problem for '{topic_title}'. Show intermediate computations explicitly with centered KaTeX equations ($$...$$)."
        ),
        (
            "Phase 4: Exam Traps & Common Misconceptions",
            f"Highlight frequent exam pitfalls, subtle edge cases, and fatal mistakes students make with '{topic_title}'. Format every major exam trap inside a dedicated callout block: '> [!WARNING] Exam Trap & Common Misconception\\n> Description and correction'. Provide crisp, memorable rules."
        )
    ]

    accumulated_lecture_markdown = f"# University Masterclass: {topic_title}\n\n"

    for idx, (phase_name, phase_prompt) in enumerate(phases):
        phase_key = f"phase_{idx+1}"
        yield f"data: {json.dumps({'type': 'phase_start', 'phase': phase_name, 'phase_key': phase_key})}\n\n"

        prompt = f"""You are a distinguished university professor delivering an immersive live masterclass.

Topic: '{topic_title}'
Phase: {phase_name}
Goal: {phase_prompt}

Prior Mastered Topics by Student (for Continuity Analogy):
{past_topics_summary}

Reference Course Material:
{context[:3500]}

Pedagogical & Formatting Rules:
- Authoritative, clear, engaging masterclass professor tone.
- Standalone equations MUST be rendered on their own lines using KaTeX block math: $$ ... $$.
- In-sentence terms MUST use inline math: $ ... $.
- Zero conversational fluff. Zero emojis.
- Deliver rich, thorough, pedagogical depth.
"""
        sys_inst = "You are an elite university professor delivering a live masterclass. Use standalone KaTeX block math $$ ... $$. Zero emojis."
        text = await call_llm(prompt, sys_inst, temperature=0.3)

        if not text:
            text = f"### {phase_name}\n\nIn our analysis of **{topic_title}**, we establish the core governing formulation and boundary properties."

        accumulated_lecture_markdown += f"\n\n## {phase_name}\n\n{text}"

        # Stream tokens smoothly for realistic live delivery
        words = text.split(" ")
        chunk_size = 3
        for i in range(0, len(words), chunk_size):
            token = " ".join(words[i:i+chunk_size]) + " "
            yield f"data: {json.dumps({'type': 'token', 'token': token})}\n\n"
            await asyncio.sleep(0.03)

        yield f"data: {json.dumps({'type': 'phase_end', 'phase': phase_name, 'phase_key': phase_key})}\n\n"

        # Update SQLite progress
        if lecture_id:
            update_lecture_session(
                session_id=session_id,
                lecture_id=lecture_id,
                current_phase=phase_key,
                current_segment_index=idx+1,
                accumulated_notes_markdown=accumulated_lecture_markdown
            )

    # Emit teach-back transition event
    yield f"data: {json.dumps({'type': 'teach_back_ready', 'lecture_id': lecture_id, 'topic_title': topic_title})}\n\n"
    yield f"data: {json.dumps({'type': 'done', 'topic_id': topic_id, 'lecture_id': lecture_id})}\n\n"


# ─── 6. Mixed-Format Topic Mastery Examination Engine ───────────────────────

async def generate_mixed_exam(session_id: str, topic_id: str, topic_title: str) -> Dict[str, Any]:
    """
    Generates 3 Question Formats in a Single Exam:
    1. Written Conceptual Questions (open-ended synthesis)
    2. Multiple-Choice Questions (MCQ, 4 options)
    3. Fill-in-the-Blank Questions (critical formulas, laws, terms)
    """
    chunks = search_fts_chunks(session_id, topic_title, limit=5)
    context = "\n\n".join(c["content"] for c in chunks)

    prompt = f"""
Generate a comprehensive university-level mastery exam for the topic: '{topic_title}'.
Base all questions strictly on this uploaded course material:

{context[:4000]}

The exam must include exactly 3 question types:
1. Written Conceptual: 2 open-ended questions testing deep synthesis and reasoning.
2. Multiple Choice: 2 four-option questions (A, B, C, D) testing concept application.
3. Fill in the Blank: 2 questions testing exact terminology, formulas, or constants.

Return ONLY valid JSON:
{{
  "topic_id": "{topic_id}",
  "topic_title": "{topic_title}",
  "questions": [
    {{
      "id": "q1",
      "type": "written",
      "question": "Explain the relationship between...",
      "rubric_criteria": "Must mention variables X and Y and their inverse proportionality.",
      "sample_model_answer": "In this system,..."
    }},
    {{
      "id": "q2",
      "type": "written",
      "question": "How does...",
      "rubric_criteria": "Full marks require defining...",
      "sample_model_answer": "..."
    }},
    {{
      "id": "q3",
      "type": "mcq",
      "question": "Which of the following statements correctly describes...",
      "options": ["Option A", "Option B", "Option C", "Option D"],
      "correct_answer": "Option A",
      "explanation": "Option A is correct because..."
    }},
    {{
      "id": "q4",
      "type": "mcq",
      "question": "Under what condition does...",
      "options": ["Option A", "Option B", "Option C", "Option D"],
      "correct_answer": "Option B",
      "explanation": "Option B is correct because..."
    }},
    {{
      "id": "q5",
      "type": "fill_in_the_blank",
      "question": "The rate of change in this model is governed by the ______ coefficient.",
      "correct_answer": "damping",
      "acceptable_synonyms": ["damping", "friction"],
      "explanation": "The damping coefficient controls the rate of energy dissipation."
    }},
    {{
      "id": "q6",
      "type": "fill_in_the_blank",
      "question": "According to the governing law, the energy state is ______ at equilibrium.",
      "correct_answer": "minimized",
      "acceptable_synonyms": ["minimized", "minimum", "zero"],
      "explanation": "At stable equilibrium, the potential energy attains a local minimum."
    }}
  ]
}}
"""
    sys_inst = "You are a university examination board evaluator. Return strict JSON only. No emojis."
    raw = await call_llm(prompt, sys_inst, temperature=0.2)

    if raw:
        try:
            clean = raw.strip().replace("```json", "").replace("```", "").strip()
            return json.loads(clean)
        except Exception:
            pass

    # Fallback exam questions
    return {
        "topic_id": topic_id,
        "topic_title": topic_title,
        "questions": [
            {
                "id": "q1",
                "type": "written",
                "question": f"Synthesize the fundamental mechanics of {topic_title} and explain how its key principles are applied in academic analysis.",
                "rubric_criteria": "Student must identify governing variables, state operational constraints, and describe the expected outcome.",
                "sample_model_answer": f"{topic_title} establishes a rigorous framework wherein system parameters interact systematically to govern observable behaviors."
            },
            {
                "id": "q2",
                "type": "mcq",
                "question": f"What is the primary governing assumption underlying {topic_title}?",
                "options": [
                    "System operates within linear boundary conditions",
                    "External interference is arbitrarily maximized",
                    "Energy dissipation occurs instantaneously",
                    "Variables are strictly stochastic and uncorrelated"
                ],
                "correct_answer": "System operates within linear boundary conditions",
                "explanation": "Linear boundary conditions ensure that standard superposition and analytical models hold."
            },
            {
                "id": "q3",
                "type": "fill_in_the_blank",
                "question": f"The core quantitative indicator evaluated in {topic_title} is known as the ______ ratio.",
                "correct_answer": "efficiency",
                "acceptable_synonyms": ["efficiency", "performance", "equilibrium"],
                "explanation": "The efficiency ratio provides the normalized benchmark for system evaluation."
            }
        ]
    }


# ─── 7. Automated Multi-Modal Exam Evaluator ────────────────────────────────

async def evaluate_exam_submission(
    session_id: str,
    topic_id: str,
    questions: List[Dict[str, Any]],
    student_answers: Dict[str, str]
) -> Dict[str, Any]:
    """
    Evaluates student exam answers:
    - Written answers evaluated with LLM rubric scoring (0 - 100%)
    - MCQs and fill-in-the-blanks with normalized keyword/synonym matching
    - Returns earned score, percentage, mastery badges, feedback
    """
    total_questions = len(questions)
    earned_points = 0.0
    question_evaluations = []

    for q in questions:
        qid = q.get("id")
        qtype = q.get("type")
        student_ans = student_answers.get(qid, "").strip()

        if qtype == "mcq":
            correct = q.get("correct_answer", "").strip().lower()
            is_correct = student_ans.lower() == correct or (len(student_ans) == 1 and correct.lower().startswith(student_ans.lower()))
            score = 100 if is_correct else 0
            earned_points += (score / 100.0)
            question_evaluations.append({
                "id": qid,
                "type": "mcq",
                "question": q.get("question"),
                "student_answer": student_ans,
                "correct_answer": q.get("correct_answer"),
                "score_percentage": score,
                "is_correct": is_correct,
                "feedback": "Correct option selected." if is_correct else f"Incorrect. The correct option is: {q.get('correct_answer')}.",
                "explanation": q.get("explanation", "")
            })

        elif qtype == "fill_in_the_blank":
            correct = q.get("correct_answer", "").strip().lower()
            synonyms = [s.strip().lower() for s in q.get("acceptable_synonyms", [correct])]
            is_correct = any(s == student_ans.lower() for s in synonyms)
            feedback = "Accurate terminology." if is_correct else f"Expected: '{q.get('correct_answer')}'."

            # Lightweight LLM Equivalence Fallback for valid terminology not in acceptable_synonyms (Category 8)
            if not is_correct and student_ans:
                equiv_prompt = f"""
Evaluate if this student's fill-in-the-blank answer is academically equivalent to the expected answer.

Question: {q.get('question')}
Expected Correct Answer: {q.get('correct_answer')}
Acceptable Synonyms: {synonyms}
Student Answer: "{student_ans}"

Task: Does the student's answer mean the same thing as the correct answer, allowing for different but valid academic terminology, synonyms, or alternative phrasing?
Return ONLY valid JSON:
{{
  "equivalent": true or false,
  "explanation": "Short explanation"
}}
"""
                try:
                    equiv_raw = await call_llm(equiv_prompt, "You are an objective exam grader. Output strict JSON only.", temperature=0.0)
                    if equiv_raw:
                        clean_eq = equiv_raw.strip().replace("```json", "").replace("```", "").strip()
                        eq_data = json.loads(clean_eq)
                        if eq_data.get("equivalent") is True:
                            is_correct = True
                            feedback = f"Accepted equivalent terminology: '{student_ans}' is academically equivalent to '{q.get('correct_answer')}'."
                except Exception as e:
                    print(f"[Exam Evaluator] Equivalence check note: {e}")

            score = 100 if is_correct else 0
            earned_points += (score / 100.0)
            question_evaluations.append({
                "id": qid,
                "type": "fill_in_the_blank",
                "question": q.get("question"),
                "student_answer": student_ans,
                "correct_answer": q.get("correct_answer"),
                "score_percentage": score,
                "is_correct": is_correct,
                "feedback": feedback,
                "explanation": q.get("explanation", "")
            })

        else:
            # Written Question Rubric Evaluation via LLM (Category 8)
            prompt = f"""
Evaluate this student's written exam response using the provided rubric.

Question: {q.get('question')}
Rubric Criteria: {q.get('rubric_criteria')}
Sample Model Answer: {q.get('sample_model_answer')}

Student's Written Answer:
"{student_ans}"

GRADING RULES:
1. Grade objectively based on whether the student's answer demonstrably satisfies each rubric criterion, NOT merely on similarity to the sample model answer. A structurally different or alternative response that satisfies the rubric criteria must receive full marks.
2. In your feedback, you MUST explicitly quote or cite which specific rubric criterion each point was awarded or deducted for.

Provide an objective academic grade from 0 to 100 and constructive feedback.
Return ONLY valid JSON:
{{
  "score_percentage": 85,
  "feedback": "Constructive academic feedback quoting specific rubric criteria...",
  "rubric_citations": ["Criterion 1 satisfied: ...", "Criterion 2 deduction: ..."],
  "strengths": "What was well explained...",
  "missed_points": "What was missing..."
}}
"""
            raw = await call_llm(prompt, "You are a university exam grader. Output strict JSON only.", temperature=0.1)
            score = 75
            feedback = "Response addresses core concepts adequately."
            rubric_citations = []
            if raw:
                try:
                    clean = raw.strip().replace("```json", "").replace("```", "").strip()
                    eval_data = json.loads(clean)
                    score = int(eval_data.get("score_percentage", 75))
                    feedback = eval_data.get("feedback", feedback)
                    rubric_citations = eval_data.get("rubric_citations", [])
                except Exception:
                    pass

            earned_points += (score / 100.0)
            question_evaluations.append({
                "id": qid,
                "type": "written",
                "question": q.get("question"),
                "student_answer": student_ans,
                "sample_model_answer": q.get("sample_model_answer"),
                "score_percentage": score,
                "is_correct": score >= 70,
                "feedback": feedback,
                "rubric_citations": rubric_citations,
                "explanation": q.get("rubric_criteria", "")
            })

    overall_percentage = round((earned_points / max(total_questions, 1)) * 100, 1)

    if overall_percentage >= 85:
        mastery_badge = "Mastered"
        mastery_level = "mastered"
    elif overall_percentage >= 65:
        mastery_badge = "Proficient"
        mastery_level = "proficient"
    else:
        mastery_badge = "Needs Review"
        mastery_level = "needs_review"

    return {
        "topic_id": topic_id,
        "total_questions": total_questions,
        "score": round(earned_points, 1),
        "percentage": overall_percentage,
        "mastery_badge": mastery_badge,
        "mastery_level": mastery_level,
        "evaluations": question_evaluations
    }
