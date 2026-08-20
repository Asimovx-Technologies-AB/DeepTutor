"""
Topic & Concept Sanitizer for DeepTutor.
Ensures extracted key topics, headings, and quiz/flashcard concept suggestions
are high-yield academic concepts and free of table artifacts, citations, and boilerplate.
"""
import re
from typing import List, Optional, Set

# Structural academic paper boilerplate sections & meta-info (not concepts to study)
BOILERPLATE_HEADINGS: Set[str] = {
    "abstract", "introduction", "conclusion", "conclusions", "references", "reference",
    "bibliography", "acknowledgment", "acknowledgments", "acknowledgements",
    "table of contents", "contents", "index", "appendix", "appendices",
    "results and discussion", "discussion", "results", "materials and methods", "methodology",
    "methods", "overview", "background", "related work", "literature review",
    "author contributions", "conflict of interest", "competing interests",
    "data availability", "ethics statement", "supplementary material",
    "characteristics of publication outputs", "publication outputs",
    "keywords", "key words", "keywords plus", "table", "figure", "figures", "tables",
    "ieee", "springer", "elsevier", "wiley", "mdpi", "arxiv", "scopus", "web of science",
    "science core collection", "sci-expanded", "thomson reuters", "google scholar",
    "proceedings", "conference", "symposium", "department", "university", "faculty",
    "edition", "published", "copyright", "rights reserved", "editorial", "preface",
    "table 1", "table 2", "table 3", "figure 1", "figure 2", "figure 3", "fig 1", "fig 2",
    "main ideas", "key themes", "core concepts", "summary overview",
    "research paper", "paper", "author biography", "biography", "about the authors",
    "bibliometric analysis", "citation history", "citation histories",
    "citation histories of the most frequently cited articles",
    "web of science categories and journals", "categories and journals",
    "open research challenges and opportunities relative to global south regions",
    "open research challenges", "research challenges", "global south regions",
    "limitations and prospects", "classical machine learning limitations and prospects",
    "funding statement", "financial support", "disclaimer", "declaration", "peer review"
}

# Substrings that disqualify candidate topic strings immediately
META_SUBSTRINGS: Set[str] = {
    "bibliometric", "citation histor", "author bio", "biography", "web of science",
    "scopus", "publication output", "conflict of interest", "acknowledg", "research paper",
    "limitations and prospect", "global south", "peer review", "copyright"
}

# Noisy stop words / country / generic tokens
STOP_WORDS: Set[str] = {
    "tc", "tp", "cpp", "lr", "roc", "usa", "uk", "china", "india", "japan", "germany",
    "south africa", "north america", "europe", "asia", "global", "international",
    "author", "authors", "editor", "volume", "issue", "pages", "journal", "p", "pp", "vol",
    "no", "num", "et al", "etc", "e g", "i e", "via", "using", "based", "approach", "paper"
}


def is_valid_academic_topic(text: str) -> bool:
    """
    Returns True only if the candidate string is a meaningful, clean technical/academic concept.
    Rejects:
      - Table column headers / code soup (e.g., 'Tpr Cpp202 Ipir Cpp202...')
      - Citation parentheticals (e.g., '(Tc2022) (C2022)', '(2021)')
      - Paper structural boilerplate ('Results and Discussion', 'Methodology', 'References')
      - Non-lexical symbol/digit strings
      - Single-letter / double-letter tokens
    """
    if not text or not isinstance(text, str):
        return False

    t = text.strip()
    # Length limits
    if len(t) < 4 or len(t) > 85:
        return False

    t_lower = t.lower()

    # 1. Exact or stripped match against boilerplate or meta substrings
    if t_lower in BOILERPLATE_HEADINGS:
        return False

    if any(sub in t_lower for sub in META_SUBSTRINGS):
        return False

    # Strip section numbering prefix like '1.2 ', 'IV. ', 'Section 3: '
    stripped_prefix = re.sub(r'^(?:(?:section|chapter|part)\s+)?(?:(?:\d+(?:\.\d+)*)|[ivxlcdm]+)[.\)\s:-]+\s*', '', t_lower).strip()
    if stripped_prefix in BOILERPLATE_HEADINGS or any(sub in stripped_prefix for sub in META_SUBSTRINGS) or len(stripped_prefix) < 3:
        return False

    # 2. Check for URLs, DOIs, file extensions, ISBNs
    if re.search(r'(?:doi:|https?://|https?:|www\.|\.pdf|\.docx?|\.txt|\.html?|isbn|issn)', t_lower):
        return False

    # 3. Check for citation artifacts, year brackets, parenthetical dumps
    # e.g., (Tc2022) (C2022), (2020), [12], (Smith et al., 2019)
    if re.search(r'et\s+al\.?', t_lower):
        return False
    if re.match(r'^\(?\s*[A-Za-z]{1,4}\d{4}\s*\)?(?:\s*\(?\s*[A-Za-z]{1,4}\d{4}\s*\)?)*$', t):
        return False
    if re.search(r'\(\s*\d{4}\s*\)', t) or re.search(r'\[\s*\d+\s*\]', t):
        return False
    if t.startswith("(") and t.endswith(")"):
        return False

    # 4. Check alphabetic letter ratio (must be >= 70% letters/spaces, not symbol/digit soup)
    letter_space_count = sum(1 for c in t if c.isalpha() or c.isspace() or c in "-'")
    if letter_space_count / max(len(t), 1) < 0.70:
        return False

    # 5. Check word composition
    words = re.findall(r'[a-zA-Z0-9]+', t)
    if not words or len(words) > 11:
        return False

    # Check for repeated word/code tokens (e.g. 'Cpp202' repeated 4 times)
    lower_words = [w.lower() for w in words]
    if len(lower_words) != len(set(lower_words)) and len(lower_words) >= 4:
        # Repetitive token soup
        return False

    # Check for alphanumeric code-words (e.g. Cpp202, Ipir202)
    alphanumeric_codes = sum(
        1 for w in words
        if len(w) >= 3 and any(c.isdigit() for c in w) and any(c.isalpha() for c in w)
    )
    if alphanumeric_codes >= 2:
        return False

    # Check for all-numbers
    if all(w.isdigit() for w in words):
        return False

    # 6. Must not be table / figure caption headers
    if re.match(r'^(?:table|figure|fig|tab|eq|equation|page|p|box)\b[.\s:-]*\d*', t_lower):
        return False

    # 7. Check if topic is just a single stop-word
    if len(words) == 1 and lower_words[0] in STOP_WORDS:
        return False

    return True


def clean_and_format_topic(topic: str) -> Optional[str]:
    """
    Sanitizes and formats a candidate topic string.
    Returns cleaned, Title Cased topic string or None if invalid.
    """
    if not is_valid_academic_topic(topic):
        return None

    t = topic.strip()

    # Strip leading numbers, bullets, colons
    t = re.sub(r'^(?:(?:section|chapter|part)\s+)?(?:(?:\d+(?:\.\d+)*)|[ivxlcdm]+)[.\)\s:-]+\s*', '', t, flags=re.IGNORECASE)
    t = re.sub(r'^[•\-\*#\s:]+', '', t)
    t = t.strip()

    # Normalize whitespace
    t = re.sub(r'\s+', ' ', t)

    if not is_valid_academic_topic(t):
        return None

    # Title case formatting if all-uppercase or all-lowercase
    if t.isupper() or t.islower():
        # Keep acronyms intact if <= 4 chars
        words = t.split()
        formatted_words = []
        for w in words:
            if len(w) <= 4 and w.isupper() and w.isalpha():
                formatted_words.append(w)
            else:
                formatted_words.append(w.capitalize())
        t = " ".join(formatted_words)

    return t


def deduplicate_and_rank_topics(topics: List[str], max_topics: int = 15) -> List[str]:
    """
    Filters, sanitizes, deduplicates, and ranks topics.
    Eliminates redundant substring overlaps (e.g. keeping longer informative concept).
    """
    cleaned_topics: List[str] = []
    seen_lower: Set[str] = set()

    for candidate in topics:
        clean = clean_and_format_topic(candidate)
        if not clean:
            continue
        c_lower = clean.lower()
        if c_lower in seen_lower:
            continue
        seen_lower.add(c_lower)
        cleaned_topics.append(clean)

    # Substring deduplication: if 'Support Vector Machines' exists, omit redundant 'Vector Machines'
    final_topics: List[str] = []
    for i, t in enumerate(cleaned_topics):
        t_lower = t.lower()
        # Check if t is an exact substring of a longer topic in the list
        is_sub = False
        for other in cleaned_topics:
            other_lower = other.lower()
            if t_lower != other_lower and t_lower in other_lower and len(other_lower) - len(t_lower) <= 25:
                # Substring overlap — keep the more specific/longer one
                is_sub = True
                break
        if not is_sub:
            final_topics.append(t)

    return final_topics[:max_topics]
