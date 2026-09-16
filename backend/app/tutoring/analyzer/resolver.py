import re
from typing import List, Dict, Any, Tuple, Optional


class ReferenceResolver:
    """
    Stage 3: Reference Resolution.
    - Pronoun Resolution (maps 'it', 'this', 'that' to previous concepts)
    - Follow-up Detection ('why?', 'tell me more', 'give an example')
    - Implicit Reference handling
    - Document & Section linking ('in chapter 2', 'on page 4')
    """

    FOLLOW_UP_PATTERNS = [
        re.compile(r"^(?:why\??|how\??|why is that\??|how so\??|explain more|tell me more|can you elaborate\??|give an example\??|what else\??)$", re.IGNORECASE),
        re.compile(r"^(?:what about|how does this relate to|can you clarify|why is that)\b", re.IGNORECASE),
    ]

    PRONOUN_PATTERN = re.compile(r"\b(it|this|that|these|those|the algorithm|the formula|the equation)\b", re.IGNORECASE)

    PAGE_SECTION_PATTERN = re.compile(r"\b(?:(?:page\s*(?:number|no\.?|#)?|p\.)\s*(\d+)|(?:chapter|section)\s*(\d+(?:\.\d+)*))\b", re.IGNORECASE)
    TABLE_PATTERN = re.compile(r"\b(table\s*(?:\d+(?:\.\d+)*|[A-Za-z]))\b|\b(the\s+table|a\s+table|this\s+table)\b", re.IGNORECASE)
    FIGURE_PATTERN = re.compile(
        r"\b(?:figure|fig\.?)\s*(\d+(?:[-.]\d+)*|[A-Za-z])\b|\b(the\s+figure|a\s+figure|this\s+figure|the\s+diagram|a\s+diagram|this\s+diagram|the\s+image|the\s+illustration)\b|\bfigure\b",
        re.IGNORECASE
    )

    GLOBAL_SCOPE_PATTERN = re.compile(
        r"\b(?:(?:this|the)\s+(?:material|meterial|document|textbook|pdf|book|syllabus|curriculum|course|subject|whole\s+material|entire\s+material)|"
        r"(?:whole|entire|complete)\s+(?:material|meterial|document|textbook|pdf|book|syllabus)|"
        r"(?:all|cover\s+all)\s+(?:the\s+)?topics|all\s+chapters|across\s+(?:all\s+)?chapters)\b",
        re.IGNORECASE
    )

    QUESTION_INDEX_PATTERNS = [
        re.compile(r"\b(?:question|q|problem|item)\s*(?:#|no\.?|num\.?)?\s*(\d+)\b", re.IGNORECASE),
        re.compile(r"\b(\d+)(?:st|nd|rd|th)\s+(?:question|q|problem|item)\b", re.IGNORECASE),
        re.compile(r"\b(first|second|third|fourth|fifth|sixth|seventh|eighth|ninth|tenth)\s+(?:question|q|problem|item)\b", re.IGNORECASE),
    ]

    WORD_TO_INDEX = {
        "first": 1, "second": 2, "third": 3, "fourth": 4, "fifth": 5,
        "sixth": 6, "seventh": 7, "eighth": 8, "ninth": 9, "tenth": 10
    }

    @classmethod
    def _extract_question_from_history(cls, conversation_history: List[Dict[str, str]], target_idx: int) -> Optional[str]:
        if not conversation_history:
            return None
        last_asst = ""
        for m in reversed(conversation_history):
            role = m.get("role") or ""
            if role in ("assistant", "tutor") or not role:
                c = (m.get("content") or m.get("text") or "").strip()
                if c and len(c) > 20:
                    last_asst = c
                    break
        if not last_asst:
            return None

        # Line-by-line scanning
        lines = last_asst.split("\n")
        idx_str = str(target_idx)
        item_pattern = re.compile(
            rf"^(?:#{{1,6}}\s*)?(?:\*{{1,2}})?(?:question|q|problem|item)?\s*{idx_str}(?:\b|[\.:\)\s-])\s*(?:\*{{1,2}})?",
            re.IGNORECASE
        )

        for line in lines:
            l = line.strip()
            if not l:
                continue
            if item_pattern.search(l):
                cleaned_line = item_pattern.sub("", l).strip()
                cleaned_line = cleaned_line.strip("*").strip(".").strip(":").strip()
                if len(cleaned_line) >= 5:
                    return cleaned_line

        return None

    @classmethod
    def resolve_references(cls, query: str, conversation_history: List[Dict[str, str]]) -> Tuple[str, Dict[str, Any]]:
        """
        Resolves ambiguous conversational references using prior turns.
        Returns: (resolved_query, resolution_meta)
        """
        resolved = query
        meta: Dict[str, Any] = {
            "is_follow_up": False,
            "resolved_pronouns": [],
            "referenced_page": None,
            "referenced_section": None,
            "referenced_table": None,
            "referenced_figure": None,
            "scope": "global" if bool(cls.GLOBAL_SCOPE_PATTERN.search(query)) else "topic",
        }

        # 1. Page and Section Reference Detection
        match = cls.PAGE_SECTION_PATTERN.search(query)
        if match:
            if match.group(1):
                meta["referenced_page"] = int(match.group(1))
            if match.group(2):
                meta["referenced_section"] = match.group(2)

        # 1b. Table Reference Detection
        table_match = cls.TABLE_PATTERN.search(query)
        if table_match:
            if table_match.group(1):
                meta["referenced_table"] = table_match.group(1).title()
            elif table_match.group(2):
                meta["referenced_table"] = "table"

        # 1d. Question Index Reference Detection (e.g. 'explain question 2', 'answer Q3', 'solve second question')
        for q_pat in cls.QUESTION_INDEX_PATTERNS:
            q_match = q_pat.search(query)
            if q_match:
                idx_val = None
                if q_match.group(1):
                    val_str = q_match.group(1).lower()
                    if val_str.isdigit():
                        idx_val = int(val_str)
                    elif val_str in cls.WORD_TO_INDEX:
                        idx_val = cls.WORD_TO_INDEX[val_str]
                if idx_val and conversation_history:
                    q_text = cls._extract_question_from_history(conversation_history, idx_val)
                    meta["referenced_question_index"] = idx_val
                    if q_text:
                        meta["referenced_question_text"] = q_text
                        resolved = f"{query}: {q_text}"
                break

        # 2. Check if query is an immediate follow-up (e.g. 'why?', 'how?', 'tell me more')
        trimmed = query.strip().lower()
        if any(pat.match(trimmed) for pat in cls.FOLLOW_UP_PATTERNS):
            meta["is_follow_up"] = True
            
            # Find the most recent distinct context turn
            last_context = ""
            for msg in reversed(conversation_history):
                c = msg.get("content", "").strip()
                if c and c.lower() != trimmed:
                    last_context = c[:120]
                    break

            if last_context:
                resolved = f"{query} regarding {last_context}"
                return resolved, meta

        # 3. Pronoun Resolution
        # If query has global scope (e.g. 'this material', 'cover all the topics') or the pronoun
        # is a specifier for a document container (e.g. 'this material', 'this textbook', 'this page'),
        # DO NOT replace it with a specific concept from previous turns!
        is_container_specifier = bool(re.search(
            r"\b(?:this|that|these|those)\s+(?:material|meterial|document|textbook|pdf|book|syllabus|curriculum|course|chapter|page|section)\b",
            query,
            re.IGNORECASE
        ))

        pronoun_match = cls.PRONOUN_PATTERN.search(query)
        if pronoun_match and conversation_history and not is_container_specifier and meta.get("scope") != "global":
            # Check the most recent turn (assistant or user) for the context being referenced
            last_msg = ""
            for m in reversed(conversation_history):
                c = (m.get("content") or "").strip()
                if c and c.lower() != trimmed:
                    last_msg = c
                    break

            skip_words = {"Tell", "Explain", "What", "How", "Why", "Show", "Can", "Please", "Describe", "Define", "Discuss", "Is", "Are", "Assistant", "Student"}

            # 1. Check for bold concepts in assistant response (e.g. **Quadratic Equation**)
            bold_nouns = re.findall(r"\*\*([^*]+)\*\*", last_msg)
            valid_nouns = [b.strip() for b in bold_nouns if len(b.strip()) > 2 and b.strip() not in skip_words]

            # 2. Check for capitalized noun phrases
            if not valid_nouns:
                key_nouns = re.findall(r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\b", last_msg)
                valid_nouns = [n for n in key_nouns if n not in skip_words]

            # 3. Check for concept in previous user queries
            if not valid_nouns:
                last_user_msg = next((m.get("content", "") for m in reversed(conversation_history) if m.get("role") == "user"), "")
                user_nouns = re.findall(r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\b", last_user_msg)
                valid_nouns = [n for n in user_nouns if n not in skip_words]
                if not valid_nouns:
                    concept_match = re.search(r"(?:what is|define|explain|about)\s+(?:a\s+|an\s+|the\s+)?([a-zA-Z\s]{3,40}?)(?:\?|$)", last_user_msg, re.IGNORECASE)
                    if concept_match and concept_match.group(1).strip():
                        valid_nouns = [concept_match.group(1).strip().title()]

            if valid_nouns:
                valid_nouns.sort(key=len, reverse=True)
                target_noun = valid_nouns[0]
                resolved = cls.PRONOUN_PATTERN.sub(target_noun, query, count=1)
                meta["resolved_pronouns"].append({"pronoun": pronoun_match.group(0), "resolved_to": target_noun})

        return resolved, meta


class CoreferencePronounResolver:
    """Convenience wrapper for ReferenceResolver with dictionary return structure."""

    @classmethod
    def resolve(cls, query: str, conversation_history: List[Dict[str, str]]) -> Dict[str, Any]:
        resolved_text, meta = ReferenceResolver.resolve_references(query, conversation_history)
        return {
            "resolved_query": resolved_text,
            "meta": meta,
        }

