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
    """Call universal LLM cascade (Gemini REST/SDK with fallback -> NVIDIA NIM -> Ollama)."""
    try:
        from app.services.study_agents import call_llm
        return await call_llm(prompt, system_instruction=system_instruction, temperature=0.1)
    except Exception:
        return ""


# ─── Boilerplate noise terms that appear in front-matter & metadata ───────────
_NOISE_WORDS = {
    "all rights reserved", "copyright", "isbn", "publication", "published",
    "publisher", "printed", "printing", "reprint", "reprinted", "edition",
    "foreword", "preface", "acknowledgement", "acknowledgements", "advisor",
    "advisors", "chief advisor", "editorial", "editor", "editors",
    "contributors", "contributor", "contents", "table of contents",
    "about the author", "about the book", "dedication", "disclaimer",
    "offices of the", "national council", "ncert", "cbse",
    "reserved", "page", "pages", "index", "glossary", "bibliography",
    "references", "appendix", "answer key", "answers",
    "www", "http", "https", "download", "website", "email",
    "price", "rs.", "rupees", "first published", "revised",
    "typeset", "cover design", "layout", "pdf", "pd 500t",
    "new delhi", "new york", "london", "cambridge",
    # Academic paper metadata & affiliations (prevent affiliation leaks)
    "university", "department", "institute", "faculty", "school of",
    "college", "laboratory", "centre", "center", "unit for data",
    "unit for", "author", "authors", "corresponding author",
    "contributions", "biography", "submitted", "accepted", "keywords",
    "abstract", "data intelligence", "mit press", "ieee", "springer",
    "elsevier", "acm", "doi:", "orcid", "issn", "volume", "issue",
    "conference", "journal", "proceedings", "street", "road",
}

_NOISE_PATTERNS = [
    r"^\d[\d\s.,-]*$",                                            # Pure numbers / dates
    r"^isbn\b",                                                    # ISBN lines
    r"^rs\.?\s*\d",                                                # Price
    r"^\(?[ivxlcdm]+\)?$",                                         # Roman numerals alone
    r"^p[gd]\s*\d",                                                # Page references like "Pd 500T"
    r"^first\s+(?:published|edition)",                             # Publication metadata
    r"^(?:revised|reprinted|printed)\b",                           # Print metadata
    r"^(?:presents|discusses|provides|describes|outlines|summarizes|explores|investigates|examines|introduces)\b", # Outline verbs
    r"\b(?:university|institute|department|faculty|school\s+of|centre|center|laboratory)\b",                      # Institutional affiliations
    r"\b(?:unit\s+for|division\s+of)\b",                           # Units / divisions
    r"^doi:\s*",                                                   # DOIs
    r"^https?://",                                                 # URLs
]


def _is_noise_heading(text: str) -> bool:
    """Returns True if the candidate heading is boilerplate/metadata, not a real topic."""
    t = text.strip().lower()
    if len(t) < 3 or len(t) > 80:
        return True
    for noise in _NOISE_WORDS:
        if noise in t:
            return True
    for pat in _NOISE_PATTERNS:
        if re.search(pat, t, re.IGNORECASE):
            return True
    alpha_chars = sum(1 for c in t if c.isalpha())
    if alpha_chars < len(t) * 0.4:
        return True
    return False


def _clean_title(t: str) -> str:
    """Strip leading numbering/prefixes like 'Chapter 1:', 'Section 2.1.', or '2.1'."""
    t = re.sub(r"^(?:Chapter|Unit|Section|Module|Part)\s*(?:\d+|[IVXLCDM]+)?[:.\s—–\-]+", "", t, flags=re.IGNORECASE)
    t = re.sub(r"^\d{1,2}(?:\.\d{1,2})*\.?\s*", "", t)
    return t.strip().rstrip(".-– ").title()


def _strip_front_matter(text: str) -> str:
    """
    Remove front-matter boilerplate (title pages, copyright, foreword) from
    the beginning of extracted text so topic extraction sees actual content.
    """
    # Look for the first real chapter/unit/section marker
    match = re.search(
        r"(?:^|\n)\s*(?:Chapter|CHAPTER|Module|MODULE|Part|PART|Unit|UNIT)\s+(?:\d+|[IVXLCDM]+|One|Two|Three|Four|Five)\b",
        text,
        re.IGNORECASE
    )
    if match and match.start() < len(text) * 0.5:
        return text[match.start():]

    # Alternative: find numbered section "1. Introduction" or "1. TOPIC NAME"
    match = re.search(
        r"(?:^|\n)\s*1[.\s]+(?:Introduction|[A-Z][A-Za-z]+)",
        text
    )
    if match and match.start() < len(text) * 0.4:
        return text[match.start():]

    # If front-matter is short (< 800 chars), skip it
    if len(text) > 2000:
        return text[600:]

    return text


def _extract_heuristic_topics(text: str, subject: str = "General Study", filename: str = "") -> List[Dict[str, Any]]:
    """Heuristic fallback topic generator when offline or no API keys present."""
    from pathlib import Path

    if (not subject or subject == "General Study") and filename:
        clean_name = Path(filename).stem.replace("_", " ").replace("-", " ").title()
        # Strip common prefixes like "Hsslive 35" or "Class 12"
        clean_name = re.sub(r"^(?:Hsslive|Class|Std|Grade)[\s\-]*\d+\s*", "", clean_name, flags=re.IGNORECASE).strip() or clean_name
        subject = clean_name

    headers = []
    seen = set()

    # Pattern 1: Section / Chapter headings at start of line
    matches = re.findall(
        r"(?:^|\n)\s*(?:Chapter|Unit|Section|Module|Part)\s+(?:\d+|[IVXLCDM]+)[:.\s—–\-]+([A-Za-z0-9\s—–,&\-()]{3,60})(?:\n|$)",
        text,
        re.IGNORECASE
    )
    for m in matches:
        t = _clean_title(m)
        if not _is_noise_heading(t) and t.lower() not in seen and len(t) > 3:
            seen.add(t.lower())
            headers.append(t)

    # Pattern 2: Numbered section headings e.g. "2.1. Decision Trees" or "2. Classical Machine Learning"
    num_matches = re.findall(
        r"(?:^|\n)\s*(\d{1,2}(?:\.\d{1,2})?)\.?\s+([A-Z][A-Za-z0-9\s—–,&\-()]{2,60})(?:\n|$)",
        text
    )
    for num, m in num_matches:
        t = _clean_title(m)
        if not _is_noise_heading(t) and t.lower() not in seen and len(t) > 3:
            seen.add(t.lower())
            headers.append(t)

    # Pattern 3: Lines in ALL CAPS (only if we still need more topics)
    if len(headers) < 4:
        caps_matches = re.findall(
            r"(?:^|\n)\s*([A-Z][A-Z0-9\s—–,&\-]{4,45})\s*(?=\n|$)",
            text
        )
        for m in caps_matches:
            t = _clean_title(m)
            if not _is_noise_heading(t) and t.lower() not in seen and len(t) > 3:
                seen.add(t.lower())
                headers.append(t)

    topics = []
    for i, h in enumerate(headers[:8]):
        topics.append({
            "id": f"topic-{i+1}",
            "title": h,
            "summary": f"Key concepts, formulas, and core problem-solving mechanics of {h}.",
            "difficulty": "Beginner" if i < 2 else ("Intermediate" if i < 5 else "Advanced"),
            "key_concepts": [f"Foundations of {h}", "Core formulas & rules", "Worked practice problems"],
            "estimated_study_time": f"{20 + (i * 5)} mins"
        })

    if not topics:
        topics = [
            {
                "id": "topic-1",
                "title": f"Foundations & Core Principles of {subject}",
                "summary": f"Introduction to primary definitions, core scope, and key formulas in {subject}.",
                "difficulty": "Beginner",
                "key_concepts": ["Primary definitions", "Fundamental laws", "Core mathematical framework"],
                "estimated_study_time": "15 mins"
            },
            {
                "id": "topic-2",
                "title": f"Key Analytical Mechanics in {subject}",
                "summary": f"In-depth breakdown of governing principles, proofs, and analytical procedures.",
                "difficulty": "Intermediate",
                "key_concepts": ["Governing mechanics", "Quantitative relations", "Analytical breakdown"],
                "estimated_study_time": "25 mins"
            },
            {
                "id": "topic-3",
                "title": f"Applied Exercises & Complex Scenarios",
                "summary": f"Worked textbook examples, multi-step problem solving, and exam preparation.",
                "difficulty": "Advanced",
                "key_concepts": ["Worked problem sets", "Edge case identification", "Exam preparation"],
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

    # 2. Strip front-matter before sending to LLM
    clean_text = _strip_front_matter(sample_text)

    # 3. LLM Topic & Relevance Extraction (<4s)
    prompt = f"""
Analyze this academic document excerpt from '{filename}' (Subject: '{subject}').

CRITICAL INSTRUCTIONS:
- IGNORE all metadata: author names, author affiliations (e.g. universities, departments, research centres, colleges), emails, citations, publication details, copyright notices, and table-of-contents page numbers.
- Extract ONLY the actual primary learning topics, concepts, chapters, or algorithms that students study in this document.
- Each topic must be a substantive academic subject or technique (e.g. 'Decision Trees', 'Support Vector Machines', 'Linear Regression') NEVER institutional affiliations or metadata.
- Provide 4 to 8 progressive topics in logical pedagogical order.

1. Validate if this is authentic academic study material.
2. Extract a progressive 4 to 8 topic learning roadmap of the actual subject matter in pedagogical order.

Return ONLY valid JSON in this exact structure:
{{
  "is_study_material": true,
  "category": "STUDY_MATERIAL",
  "reason": "Authentic academic textbook/lecture material.",
  "topics": [
    {{
      "id": "topic-1",
      "title": "Actual Academic Topic Name",
      "summary": "1-2 sentence summary of what students learn in this topic.",
      "difficulty": "Beginner",
      "key_concepts": ["Concept 1", "Concept 2", "Concept 3"],
      "estimated_study_time": "20 mins"
    }}
  ]
}}

Document Excerpt:
{clean_text[:18000]}
"""

    sys_inst = "You are a university dean and expert curriculum architect. Extract only real academic topics that students study — never author affiliations, universities, publisher metadata, ISBNs, editor names, or copyright text. Return strict JSON only without markdown code blocks."
    raw = await _invoke_llm(prompt, sys_inst)

    if raw:
        try:
            cleaned = raw.strip()
            if cleaned.startswith("```json"):
                cleaned = cleaned[7:]
            if cleaned.startswith("```"):
                cleaned = cleaned[3:]
            if cleaned.endswith("```"):
                cleaned = cleaned[:-3]
            data = json.loads(cleaned.strip())

            is_study = data.get("is_study_material", True)
            reason = data.get("reason", "Academic material accepted.")
            topics = data.get("topics", [])

            if not is_study:
                return False, reason, []

            if topics and isinstance(topics, list):
                # Filter out any noise topics that slipped through
                valid_topics = []
                for t in topics:
                    title = t.get("title", "")
                    if not _is_noise_heading(title):
                        valid_topics.append(t)

                # Ensure ids and difficulties
                for i, t in enumerate(valid_topics):
                    if not t.get("id"):
                        t["id"] = f"topic-{i+1}"
                    if not t.get("difficulty"):
                        t["difficulty"] = "Intermediate"
                    if not t.get("estimated_study_time"):
                        t["estimated_study_time"] = "20 mins"

                if len(valid_topics) >= 2:
                    return True, reason, valid_topics
        except Exception:
            pass

    # Heuristic fallback if LLM offline
    fallback_topics = _extract_heuristic_topics(sample_text, subject=subject, filename=filename)
    return True, "Study material accepted and curriculum mapped.", fallback_topics
