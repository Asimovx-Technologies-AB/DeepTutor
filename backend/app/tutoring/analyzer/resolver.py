import re
from typing import List, Dict, Any, Tuple, Optional
from sqlalchemy.orm import Session
from app.models.artifact import GeneratedArtifact, GeneratedArtifactItem


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
        re.compile(r"\b(?:question|q|problem|item)\s*(?:#|no\.?|num\.?)?\s*(\d+)(?:\s+(?:from|in|of)\s+(?:the\s+)?([a-zA-Z0-9_\-\s]+))?\b", re.IGNORECASE),
        re.compile(r"\b(\d+)(?:st|nd|rd|th)\s+(?:question|q|problem|item)(?:\s+(?:from|in|of)\s+(?:the\s+)?([a-zA-Z0-9_\-\s]+))?\b", re.IGNORECASE),
        re.compile(r"\b(first|second|third|fourth|fifth|sixth|seventh|eighth|ninth|tenth)\s+(?:question|q|problem|item)(?:\s+(?:from|in|of)\s+(?:the\s+)?([a-zA-Z0-9_\-\s]+))?\b", re.IGNORECASE),
    ]

    WORD_TO_INDEX = {
        "first": 1, "second": 2, "third": 3, "fourth": 4, "fifth": 5,
        "sixth": 6, "seventh": 7, "eighth": 8, "ninth": 9, "tenth": 10
    }

    @classmethod
    def _extract_question_from_history(
        cls,
        conversation_history: List[Dict[str, str]],
        target_idx: int,
        target_heading: Optional[str] = None
    ) -> Optional[str]:
        if not conversation_history:
            return None

        # Scan all past assistant messages from newest to oldest
        candidate_messages = []
        for m in reversed(conversation_history):
            role = m.get("role") or ""
            if role in ("assistant", "tutor") or not role:
                c = (m.get("content") or m.get("text") or "").strip()
                if c and len(c) > 20:
                    candidate_messages.append(c)

        if not candidate_messages:
            return None

        idx_str = str(target_idx)
        item_pattern = re.compile(
            rf"^(?:#{{1,6}}\s*)?(?:\*{{1,2}})?(?:question|q|problem|item)?\s*{idx_str}(?:\b|[\.:\)\s-])\s*(?:\*{{1,2}})?",
            re.IGNORECASE
        )

        # Prioritize messages matching topic/heading if provided
        if target_heading:
            th_lower = target_heading.strip().lower()
            matching_msgs = [c for c in candidate_messages if th_lower in c.lower()]
            ordered_candidates = matching_msgs + [c for c in candidate_messages if c not in matching_msgs]
        else:
            ordered_candidates = candidate_messages

        for asst_text in ordered_candidates:
            lines = asst_text.split("\n")
            # Extract set heading if present (e.g., ### 📝 Practice Questions: Isomerism)
            set_heading = None
            for line in lines:
                l_strip = line.strip()
                if l_strip.startswith("#"):
                    clean_h = l_strip.lstrip("#").strip()
                    if any(w in clean_h.lower() for w in ["question", "practice", "exam", "quiz", "problem"]):
                        set_heading = clean_h
                        break

            for line in lines:
                l = line.strip()
                if not l:
                    continue
                if item_pattern.search(l):
                    cleaned_line = item_pattern.sub("", l).strip()
                    cleaned_line = cleaned_line.strip("*").strip(".").strip(":").strip()
                    if len(cleaned_line) >= 5:
                        if set_heading:
                            return f"[{set_heading}] {cleaned_line}"
                        return cleaned_line

        return None

    @classmethod
    def resolve_references(cls, query: str, conversation_history: List[Dict[str, str]], db_session: Optional[Session] = None, session_id: Optional[str] = None) -> Tuple[str, Dict[str, Any]]:
        """
        Resolves ambiguous conversational references using prior turns or structured artifact memory.
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
                heading_val = None
                if q_match.group(1):
                    val_str = q_match.group(1).lower()
                    if val_str.isdigit():
                        idx_val = int(val_str)
                    elif val_str in cls.WORD_TO_INDEX:
                        idx_val = cls.WORD_TO_INDEX[val_str]
                if len(q_match.groups()) > 1 and q_match.group(2):
                    heading_val = q_match.group(2).strip()
                    
                if idx_val:
                    meta["referenced_question_index"] = idx_val
                    if heading_val:
                        meta["referenced_artifact_heading"] = heading_val
                        
                    # Attempt DB Artifact Resolution first
                    if db_session and session_id:
                        query_artifacts = db_session.query(GeneratedArtifact).filter(GeneratedArtifact.session_id == session_id)
                        
                        target_artifact = None
                        is_ambiguous = False
                        
                        if heading_val:
                            # Try semantic string match against title
                            artifacts = query_artifacts.all()
                            matches = [a for a in artifacts if a.title and heading_val.lower() in a.title.lower()]
                            if matches:
                                target_artifact = matches[0]
                        else:
                            # Fetch active artifact from session if exists, otherwise fallback to recent
                            from app.models.session import StudySession
                            sess = db_session.query(StudySession).filter(StudySession.id == session_id).first()
                            active_id = sess.session_metadata.get("active_artifact_id") if sess and sess.session_metadata else None
                            
                            if active_id:
                                target_artifact = query_artifacts.filter(GeneratedArtifact.id == active_id).first()
                            else:
                                recent_artifacts = query_artifacts.order_by(GeneratedArtifact.created_at.desc()).limit(2).all()
                                if len(recent_artifacts) > 1 and recent_artifacts[0].artifact_type == recent_artifacts[1].artifact_type:
                                    is_ambiguous = True
                                elif recent_artifacts:
                                    target_artifact = recent_artifacts[0]
                                    
                        if is_ambiguous:
                            meta["ambiguity_status"] = "AMBIGUOUS"
                            meta["reference_type"] = "NONE"
                        elif target_artifact:
                            item = db_session.query(GeneratedArtifactItem).filter(
                                GeneratedArtifactItem.artifact_id == target_artifact.id,
                                GeneratedArtifactItem.item_index == idx_val
                            ).first()
                            
                            if item:
                                resolved = f"Explain the following generated practice question:\n\n{item.content}"
                                meta["reference_type"] = "GENERATED_QUESTION" if target_artifact.artifact_type in ("PRACTICE_QUESTION_SET", "QUIZ") else target_artifact.artifact_type
                                meta["reference_index"] = idx_val
                                meta["artifact_id"] = target_artifact.id
                                meta["artifact_item_id"] = item.id
                                meta["resolved_topic"] = item.topic or target_artifact.topic
                                meta["ambiguity_status"] = "RESOLVED_FROM_CONTEXT"
                                return resolved, meta
                                
                    # Fallback to chat history parsing if DB lookup failed or unavailable
                    if conversation_history:
                        q_text = cls._extract_question_from_history(conversation_history, idx_val, target_heading=heading_val)
                        if q_text:
                            meta["referenced_question_text"] = q_text
                            resolved = f"{query}: {q_text}"
                break

        # 2. Check if query is an immediate follow-up (e.g. 'why?', 'how?', 'tell me more', 'give me an example')
        trimmed = query.strip().lower()

        # Find active concept from history
        active_concept = cls._extract_active_concept(conversation_history)

        # 2a. Ellipsis / Partial follow-up patterns
        what_about_match = re.match(r"^(?:what\s+about|how\s+about)\s+(.+?)[?!.]*$", trimmed, re.IGNORECASE)
        if what_about_match and active_concept:
            sub_concept = what_about_match.group(1).strip()
            # If the sub_concept doesn't already mention active_concept
            if active_concept.lower() not in sub_concept.lower():
                resolved = f"What is {sub_concept} in {active_concept}?"
                meta["is_follow_up"] = True
                meta["resolved_concept"] = active_concept
                meta["resolved_subconcept"] = sub_concept
                return resolved, meta

        example_match = re.match(r"^(?:give\s+(?:me\s+)?(?:an\s+|another\s+)?example|provide\s+an\s+example|show\s+an\s+example)[?!.]*$", trimmed, re.IGNORECASE)
        if example_match and active_concept:
            resolved = f"Give an example of {active_concept}."
            meta["is_follow_up"] = True
            meta["resolved_concept"] = active_concept
            return resolved, meta

        simplify_match = re.match(r"^(?:simplify(?:\s+this)?|explain\s+simply|explain\s+like\s+i'm\s+(?:a\s+)?beginner|make\s+it\s+simpler)[?!.]*$", trimmed, re.IGNORECASE)
        if simplify_match and active_concept:
            resolved = f"Simplify the explanation of {active_concept}."
            meta["is_follow_up"] = True
            meta["resolved_concept"] = active_concept
            return resolved, meta

        if any(pat.match(trimmed) for pat in cls.FOLLOW_UP_PATTERNS):
            meta["is_follow_up"] = True
            
            # Find the most recent distinct context turn
            last_context = active_concept
            if not last_context:
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
            target_noun = active_concept
            if not target_noun:
                # Fallback to scanning last message
                last_msg = ""
                for m in reversed(conversation_history):
                    c = (m.get("content") or "").strip()
                    if c and c.lower() != trimmed:
                        last_msg = c
                        break
                skip_words = {"Tell", "Explain", "What", "How", "Why", "Show", "Can", "Please", "Describe", "Define", "Discuss", "Is", "Are", "Assistant", "Student"}
                bold_nouns = re.findall(r"\*\*([^*]+)\*\*", last_msg)
                valid_nouns = [b.strip() for b in bold_nouns if len(b.strip()) > 2 and b.strip() not in skip_words]
                if valid_nouns:
                    target_noun = valid_nouns[0]

            if target_noun:
                resolved = cls.PRONOUN_PATTERN.sub(target_noun, query, count=1)
                meta["resolved_pronouns"].append({"pronoun": pronoun_match.group(0), "resolved_to": target_noun})

        return resolved, meta

    @classmethod
    def _extract_active_concept(cls, conversation_history: List[Dict[str, str]]) -> Optional[str]:
        if not conversation_history:
            return None

        skip_words = {
            "tell", "explain", "what", "how", "why", "show", "can", "please",
            "describe", "define", "discuss", "is", "are", "assistant", "student",
            "user", "tutor", "yes", "no", "ok", "okay", "thanks", "hello", "hi"
        }

        # 1. Look for user queries with "what is X", "explain X", "tell me about X"
        for m in reversed(conversation_history):
            if m.get("role") == "user":
                txt = m.get("content", "").strip()
                # Pattern: explain / what is / tell me about / about X
                match = re.search(
                    r"(?:explain|what is|tell me about|about|teach me|study|notes on|questions on|compare)\s+(?:a\s+|an\s+|the\s+)?([a-zA-Z0-9_\-\s]{2,50}?)(?:\?|\.|$)",
                    txt,
                    re.IGNORECASE
                )
                if match:
                    concept = match.group(1).strip()
                    if concept.lower() not in skip_words and len(concept) > 1:
                        return concept

        # 2. Check for bold concepts in assistant responses (e.g. **Support Vector Machines**)
        for m in reversed(conversation_history):
            if m.get("role") in ("assistant", "tutor"):
                txt = m.get("content", "").strip()
                bolds = re.findall(r"\*\*([^*]+)\*\*", txt)
                valid = [b.strip() for b in bolds if len(b.strip()) > 2 and b.strip().lower() not in skip_words]
                if valid:
                    return valid[0]

        return None

    @classmethod
    def build_compact_context(
        cls,
        conversation_history: List[Dict[str, str]],
        current_subject: Optional[str] = None,
        current_topic: Optional[str] = None,
        max_turns: int = 4
    ) -> Dict[str, Any]:
        """
        Produces a compact, token-efficient representation of recent dialogue context
        for the Query Analyzer LLM.
        """
        recent_turns = []
        for msg in conversation_history[-max_turns:]:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            # Truncate assistant content to preserve token budget
            if role in ("assistant", "tutor") and len(content) > 200:
                content = content[:200] + "..."
            recent_turns.append({"role": role, "content": content})

        active_concept = cls._extract_active_concept(conversation_history) or current_topic

        return {
            "recent_turns": recent_turns,
            "active_concept": active_concept,
            "current_subject": current_subject,
            "current_topic": current_topic,
            "total_turns_count": len(conversation_history)
        }


class CoreferencePronounResolver:
    """Convenience wrapper for ReferenceResolver with dictionary return structure."""

    @classmethod
    def resolve(cls, query: str, conversation_history: List[Dict[str, str]], db_session: Optional[Session] = None, session_id: Optional[str] = None) -> Dict[str, Any]:
        resolved_text, meta = ReferenceResolver.resolve_references(query, conversation_history, db_session, session_id)
        return {
            "resolved_query": resolved_text,
            "meta": meta,
        }

