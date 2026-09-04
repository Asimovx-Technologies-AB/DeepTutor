"""
Direct Kerala SCERT Class 10 Textbook Catalog & Context Extractor.
Provides guaranteed grounding in official curriculum textbooks for:
  - Class 10 Mathematics (Hsslive-35_Maths Eng.pdf)
  - Class 10 Physics (Hsslive-15_Physics Eng.pdf)
  - Class 10 Chemistry (Hsslive-19_Chemistry Eng.pdf)
"""
import os
import re
from pathlib import Path
from typing import List, Dict, Optional, Tuple

# Locate TextBook folder relative to backend
backend_dir = Path(__file__).resolve().parent.parent.parent
textbook_dir = backend_dir.parent / "TextBook"

CURRICULUM_CATALOG: Dict[str, Dict] = {
    # Mathematics Full Textbook (Part 1 - 7 Chapters)
    "sslc-math": {
        "pdf_name": "Hsslive-35_Maths Eng.pdf",
        "subject_name": "Class 10 Mathematics",
        "title": "Class 10 Mathematics",
        "pages": list(range(7, 153)),
    },
    "math-10-1": {
        "pdf_name": "Hsslive-35_Maths Eng.pdf",
        "subject_name": "Class 10 Mathematics",
        "title": "Arithmetic Sequences",
        "pages": list(range(7, 31)),
    },
    "math-10-2": {
        "pdf_name": "Hsslive-35_Maths Eng.pdf",
        "subject_name": "Class 10 Mathematics",
        "title": "Circles and Angles",
        "pages": list(range(31, 59)),
    },
    "math-10-3": {
        "pdf_name": "Hsslive-35_Maths Eng.pdf",
        "subject_name": "Class 10 Mathematics",
        "title": "Arithmetic Sequences & Algebra",
        "pages": list(range(59, 73)),
    },
    "math-10-4": {
        "pdf_name": "Hsslive-35_Maths Eng.pdf",
        "subject_name": "Class 10 Mathematics",
        "title": "Mathematics of Chance",
        "pages": list(range(73, 85)),
    },
    "math-10-5": {
        "pdf_name": "Hsslive-35_Maths Eng.pdf",
        "subject_name": "Class 10 Mathematics",
        "title": "Second Degree Equations",
        "pages": list(range(85, 97)),
    },
    "math-10-6": {
        "pdf_name": "Hsslive-35_Maths Eng.pdf",
        "subject_name": "Class 10 Mathematics",
        "title": "Trigonometry",
        "pages": list(range(97, 127)),
    },
    "math-10-7": {
        "pdf_name": "Hsslive-35_Maths Eng.pdf",
        "subject_name": "Class 10 Mathematics",
        "title": "Coordinates",
        "pages": list(range(127, 153)),
    },

    # Physics Full Textbook (Part 1 - 4 Chapters)
    "sslc-physics": {
        "pdf_name": "Hsslive-15_Physics Eng.pdf",
        "subject_name": "Class 10 Physics",
        "title": "Class 10 Physics",
        "pages": list(range(7, 89)),
    },
    "phys-10-1": {
        "pdf_name": "Hsslive-15_Physics Eng.pdf",
        "subject_name": "Class 10 Physics",
        "title": "Wave Motion & Oscillations",
        "pages": list(range(7, 27)),
    },
    "phys-10-2": {
        "pdf_name": "Hsslive-15_Physics Eng.pdf",
        "subject_name": "Class 10 Physics",
        "title": "Refraction of Light & Lenses",
        "pages": list(range(27, 49)),
    },
    "phys-10-3": {
        "pdf_name": "Hsslive-15_Physics Eng.pdf",
        "subject_name": "Class 10 Physics",
        "title": "Dispersion of Light & Colour",
        "pages": list(range(49, 69)),
    },
    "phys-10-4": {
        "pdf_name": "Hsslive-15_Physics Eng.pdf",
        "subject_name": "Class 10 Physics",
        "title": "Magnetic Effect of Electric Current",
        "pages": list(range(69, 89)),
    },

    # Chemistry Full Textbook (Part 1 - 4 Units)
    "sslc-chemistry": {
        "pdf_name": "Hsslive-19_Chemistry Eng.pdf",
        "subject_name": "Class 10 Chemistry",
        "title": "Class 10 Chemistry",
        "pages": list(range(1, 97)),
    },
    "chem-10-1": {
        "pdf_name": "Hsslive-19_Chemistry Eng.pdf",
        "subject_name": "Class 10 Chemistry",
        "title": "Nomenclature of Organic Compounds & Isomerism",
        "pages": list(range(1, 33)),
    },
    "chem-10-2": {
        "pdf_name": "Hsslive-19_Chemistry Eng.pdf",
        "subject_name": "Class 10 Chemistry",
        "title": "Chemical Reactions of Organic Compounds",
        "pages": list(range(33, 49)),
    },
    "chem-10-3": {
        "pdf_name": "Hsslive-19_Chemistry Eng.pdf",
        "subject_name": "Class 10 Chemistry",
        "title": "Periodic Table & Electron Configuration",
        "pages": list(range(49, 73)),
    },
    "chem-10-4": {
        "pdf_name": "Hsslive-19_Chemistry Eng.pdf",
        "subject_name": "Class 10 Chemistry",
        "title": "Gas Laws and Mole Concept",
        "pages": list(range(73, 97)),
    },
}

TOPIC_ALIASES = {
    "math": "sslc-math",
    "maths": "sslc-math",
    "mathematics": "sslc-math",
    "physics": "sslc-physics",
    "chemistry": "sslc-chemistry",
    "sslc_math": "sslc-math",
    "sslc_physics": "sslc-physics",
    "sslc_chemistry": "sslc-chemistry",
}


def is_curriculum_topic(topic_id: Optional[str]) -> bool:
    """Check if topic_id is a curriculum subject or chapter."""
    if not topic_id:
        return False
    t = str(topic_id).lower().strip()
    if t in CURRICULUM_CATALOG or t in TOPIC_ALIASES:
        return True
    return t.startswith(("sslc-", "math-10-", "phys-10-", "chem-10-", "math-", "phys-", "chem-", "textbook"))


def get_curriculum_info(topic_id: Optional[str]) -> Optional[Dict]:
    """Get metadata and page configuration for a curriculum topic."""
    if not topic_id:
        return None
    t = str(topic_id).lower().strip()
    norm_t = TOPIC_ALIASES.get(t, t)
    return CURRICULUM_CATALOG.get(norm_t)


def get_chapter_title(topic_id: Optional[str]) -> str:
    """Get canonical chapter or subject title."""
    info = get_curriculum_info(topic_id)
    if info:
        return info["title"]
    if not topic_id:
        return "This Section"
    return str(topic_id).replace("-", " ").replace("_", " ").title()


def extract_textbook_chunks(
    topic_id: str,
    query: Optional[str] = None,
    max_chunks: int = 12,
) -> List[str]:
    """
    Directly extracts rich, grounded text chunks from the official Kerala SCERT
    textbook PDF for the given curriculum topic/chapter.
    """
    info = get_curriculum_info(topic_id)
    if not info:
        return []

    pdf_path = textbook_dir / info["pdf_name"]
    if not pdf_path.exists():
        return []

    try:
        import pypdf
        reader = pypdf.PdfReader(str(pdf_path))
        extracted_page_texts: List[Tuple[int, str]] = []
        target_pages = set(info["pages"])

        for p_idx, page in enumerate(reader.pages):
            page_num = p_idx + 1
            if page_num in target_pages:
                txt = page.extract_text() or ""
                txt = txt.strip()
                if txt and len(txt) > 40:
                    extracted_page_texts.append((page_num, txt))

        raw_chunks: List[Dict] = []
        for page_num, p_text in extracted_page_texts:
            paragraphs = [p.strip() for p in re.split(r'\n\s*\n+', p_text) if len(p.strip()) > 50]
            for p in paragraphs:
                header = f"[{info['subject_name']} - {info['title']} (Page {page_num})]"
                full_chunk = f"{header}\n{p}"
                raw_chunks.append({
                    "text": full_chunk,
                    "page": page_num,
                    "content": p.lower(),
                })

        if not raw_chunks:
            for page_num, p_text in extracted_page_texts:
                header = f"[{info['subject_name']} - {info['title']} (Page {page_num})]"
                raw_chunks.append({
                    "text": f"{header}\n{p_text[:1200]}",
                    "page": page_num,
                    "content": p_text.lower(),
                })

        if query and query.strip():
            q_terms = [w.lower() for w in re.findall(r'\w+', query) if len(w) > 2]
            def score_chunk(c: Dict) -> int:
                return sum(c["content"].count(term) for term in q_terms)
            scored_chunks = sorted(raw_chunks, key=score_chunk, reverse=True)
            selected = [c["text"] for c in scored_chunks[:max_chunks]]
            if selected:
                return selected

        if len(raw_chunks) <= max_chunks:
            return [c["text"] for c in raw_chunks]

        step = max(1, len(raw_chunks) // max_chunks)
        sampled = raw_chunks[::step][:max_chunks]
        return [c["text"] for c in sampled]

    except Exception as e:
        print(f"[curriculum_catalog] Error reading {pdf_path}: {e}")
        return []
