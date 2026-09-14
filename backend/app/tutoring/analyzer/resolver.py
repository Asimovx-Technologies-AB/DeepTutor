import re
from typing import List, Dict, Any, Tuple


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
        pronoun_match = cls.PRONOUN_PATTERN.search(query)
        if pronoun_match and conversation_history:
            last_user_msg = next((m["content"] for m in reversed(conversation_history) if m["role"] == "user"), "")
            # Extract key noun phrases from previous turn
            key_nouns = re.findall(r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\b", last_user_msg)
            # Filter out common command words
            skip_words = {"Tell", "Explain", "What", "How", "Why", "Show", "Can", "Please", "Describe", "Define", "Discuss", "Is", "Are"}
            valid_nouns = [n for n in key_nouns if n not in skip_words]
            if valid_nouns:
                # Prefer longest phrase (e.g. "Support Vector Machines")
                valid_nouns.sort(key=len, reverse=True)
                target_noun = valid_nouns[0]
                resolved = cls.PRONOUN_PATTERN.sub(target_noun, query, count=1)
                meta["resolved_pronouns"].append({"pronoun": pronoun_match.group(0), "resolved_to": target_noun})

        return resolved, meta
