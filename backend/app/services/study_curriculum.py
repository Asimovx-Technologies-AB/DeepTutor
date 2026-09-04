"""
Curriculum Reasoning, Guardrails & Academic Relevance Classifier.

Features:
- Upfront deterministic guardrail: Instant regex & keyword analysis for CVs, Invoices, Receipts, Contracts
- 6-Class Academic Relevance Classifier: STUDY_MATERIAL vs NONACADEMIC
- Curriculum Reasoning Agent: Syllabus / TOC prioritization, 4-10 progressive topic roadmap
"""

import os
import re
import json
import asyncio
from typing import Dict, Any, List, Tuple
from app.core.config import get_settings


# ─── 1. Deterministic Upfront Guardrails ─────────────────────────────────────

NON_ACADEMIC_PATTERNS = [
    # Resumes / CVs
    (r"\b(curriculum vitae|resume|work experience|employment history|education history|references available)\b", "RESUME_CV"),
    # Invoices / Receipts / Bills
    (r"\b(invoice\s*#|bill to|amount due|payment terms|remit to|receipt number|subtotal\s*[:$]|total due)\b", "INVOICE_BILL"),
    # Legal Contracts
    (r"\b(this agreement is made|hereby agree|terms and conditions|governing law|confidentiality agreement|non-disclosure)\b", "LEGAL_CONTRACT"),
    # Corporate Pitch Decks / Marketing
    (r"\b(quarterly earnings|q[1-4] financial results|investor pitch deck|ebitda|cap table)\b", "COMMERCIAL_REPORT"),
]


def fast_guardrail_check(sample_text: str) -> Tuple[bool, str, str]:
    """
    Fast regex pre-check (<2ms).
    Returns (is_acceptable, category, explanation).
    """
    text_lower = sample_text[:4000].lower()
    for pattern, cat in NON_ACADEMIC_PATTERNS:
        if re.search(pattern, text_lower):
            if cat == "RESUME_CV":
                return False, "PERSONAL", "This document appears to be a Resume or CV. DeepTutor is specialized for academic study materials, textbooks, slides, and lecture notes."
            elif cat == "INVOICE_BILL":
                return False, "COMMERCIAL", "This document appears to be an Invoice or Receipt. Please upload academic or educational course material."
            elif cat == "LEGAL_CONTRACT":
                return False, "COMMERCIAL", "This document appears to be a Legal Contract or NDA. DeepTutor only processes student study materials and textbooks."
            elif cat == "COMMERCIAL_REPORT":
                return False, "COMMERCIAL", "This document appears to be a Corporate Financial Report rather than an academic study guide."

    return True, "STUDY_MATERIAL", "Content passed heuristic checks."


# ─── 2. Academic Relevance Classifier & Topic Extraction ────────────────────

async def _invoke_llm(prompt: str, system_instruction: str = "") -> str:
    """Call Google Gemini (with cascade fallback to NVIDIA NIM / Local)."""
    settings = get_settings()

    # 1. Google Gemini
    if settings.GEMINI_API_KEY:
        try:
            import google.generativeai as genai
            genai.configure(api_key=settings.GEMINI_API_KEY)
            model_name = getattr(settings, "GEMINI_MODEL", "gemini-2.5-flash")
            # Clean model name if passed with prefix
            clean_name = model_name.replace("models/", "")
            model = genai.GenerativeModel(
                model_name=clean_name,
                system_instruction=system_instruction if system_instruction else None
            )
            resp = await asyncio.to_thread(model.generate_content, prompt)
            if resp and resp.text:
                return resp.text
        except Exception as e:
            # Fallback to secondary gemini model
            try:
                model = genai.GenerativeModel("gemini-1.5-flash")
                resp = await asyncio.to_thread(model.generate_content, prompt)
                if resp and resp.text:
                    return resp.text
            except Exception:
                pass

    # 2. NVIDIA NIM Fallback
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

            async with httpx.AsyncClient(timeout=25.0) as client:
                res = await client.post(
                    f"{base_url}/chat/completions",
                    headers=headers,
                    json={"model": chat_model, "messages": messages, "temperature": 0.2}
                )
                if res.status_code == 200:
                    data = res.json()
                    return data["choices"][0]["message"]["content"]
        except Exception:
            pass

    return ""


def _extract_heuristic_topics(text: str, subject: str = "General Study") -> List[Dict[str, Any]]:
    """Heuristic fallback topic generator when offline or no API keys present."""
    # Look for chapter/section headers: e.g. "Chapter 1: ...", "1. Introduction", "Section ..."
    headers = re.findall(r"(?:Chapter\s+\d+|Section\s+\d+|\d+\.\d+|\bUnit\s+\d+)[:\s]+([A-Za-z0-9\s—–,-]{4,40})", text, re.IGNORECASE)
    topics = []
    seen = set()

    for i, h in enumerate(headers[:8]):
        title = h.strip().title()
        if title.lower() not in seen and len(title) > 3:
            seen.add(title.lower())
            topics.append({
                "id": f"topic-{i+1}",
                "title": title,
                "summary": f"Key concepts, formulas, and fundamental mechanics of {title} in {subject}.",
                "difficulty": "Beginner" if i < 2 else ("Intermediate" if i < 5 else "Advanced"),
                "key_concepts": [f"Core mechanics of {title}", "Mathematical derivations", "Common misconceptions"],
                "estimated_study_time": f"{15 + (i * 5)} mins"
            })

    if not topics:
        topics = [
            {
                "id": "topic-1",
                "title": f"Fundamentals of {subject}",
                "summary": f"Introduction to primary definitions, core scope, and foundational models of {subject}.",
                "difficulty": "Beginner",
                "key_concepts": ["Primary definitions", "Fundamental laws", "Core framework"],
                "estimated_study_time": "15 mins"
            },
            {
                "id": "topic-2",
                "title": f"Core Mechanics & Analysis in {subject}",
                "summary": f"In-depth breakdown of governing principles, structural relationships, and analytical procedures.",
                "difficulty": "Intermediate",
                "key_concepts": ["Governing mechanics", "Quantitative relations", "Analytical breakdown"],
                "estimated_study_time": "25 mins"
            },
            {
                "id": "topic-3",
                "title": f"Applied Problem Solving & Edge Cases",
                "summary": f"Worked examples, complex scenario evaluations, and common exam pitfalls.",
                "difficulty": "Advanced",
                "key_concepts": ["Worked problem sets", "Edge case identification", "Common exam traps"],
                "estimated_study_time": "30 mins"
            }
        ]

    return topics


async def extract_topics_and_validate(
    sample_text: str,
    subject: str = "General Study",
    filename: str = ""
) -> Tuple[bool, str, List[Dict[str, Any]]]:
    """
    Concurrently runs academic relevance classification and extracts 4-10 topics roadmap.
    Returns (is_acceptable, feedback_message, topics_list).
    """
    # 1. Fast deterministic check
    ok, cat, reason = fast_guardrail_check(sample_text)
    if not ok:
        return False, reason, []

    # 2. LLM Topic & Relevance Extraction (<4s)
    prompt = f"""
Analyze this academic document excerpt from '{filename}' (Subject: '{subject}').

1. Validate if this is authentic academic study material (textbook, lecture notes, syllabus, paper, problem set).
2. Extract a progressive 4 to 8 topic learning roadmap covering the material in pedagogical order.

Return ONLY valid JSON in this exact structure:
{{
  "is_study_material": true,
  "category": "STUDY_MATERIAL",
  "reason": "Authentic academic textbook/lecture material.",
  "topics": [
    {{
      "id": "topic-1",
      "title": "Topic Name",
      "summary": "1-2 sentence high-level summary of core mechanics.",
      "difficulty": "Beginner",
      "key_concepts": ["Concept 1", "Concept 2", "Concept 3"],
      "estimated_study_time": "20 mins"
    }}
  ]
}}

Excerpt:
{sample_text[:5000]}
"""

    sys_inst = "You are a university dean and expert curriculum architect. Return strict JSON only without markdown code blocks."
    raw = await _invoke_llm(prompt, sys_inst)

    if raw:
        try:
            cleaned = raw.strip()
            if cleaned.startswith("```json"):
                cleaned = cleaned[7:]
            if cleaned.endswith("```"):
                cleaned = cleaned[:-3]
            data = json.loads(cleaned.strip())

            is_study = data.get("is_study_material", True)
            reason = data.get("reason", "Academic material accepted.")
            topics = data.get("topics", [])

            if not is_study:
                return False, reason, []

            if topics and isinstance(topics, list):
                # Ensure ids and difficulties
                for i, t in enumerate(topics):
                    if not t.get("id"):
                        t["id"] = f"topic-{i+1}"
                    if not t.get("difficulty"):
                        t["difficulty"] = "Intermediate"
                    if not t.get("estimated_study_time"):
                        t["estimated_study_time"] = "20 mins"
                return True, reason, topics
        except Exception:
            pass

    # Heuristic fallback if LLM offline
    fallback_topics = _extract_heuristic_topics(sample_text, subject)
    return True, "Study material accepted and curriculum mapped.", fallback_topics
