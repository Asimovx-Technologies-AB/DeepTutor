import re
from typing import List, Dict, Any
from app.schemas.tutoring import QueryMetadata


class QueryUnderstanding:
    """
    Stage 4: Query Understanding.
    - Intent Detection (Q&A, Explanation, Comparison, Casual, Summary, Quiz, Problem Solving)
    - Topic & Entity Extraction
    - Learning Objective (Bloom's Taxonomy)
    - Difficulty & Complexity Assessment
    - Response Requirements (needs LaTeX math, tables, steps)
    """

    CASUAL_PATTERNS = [
        re.compile(r"^(?:hi|hello|hey|good\s+(?:morning|afternoon|evening)|greetings|who\s+are\s+you)\b", re.IGNORECASE),
        re.compile(r"^(?:thanks|thank\s+you|awesome|cool|bye|goodbye)\b", re.IGNORECASE),
    ]

    SUMMARY_PATTERNS = [
        re.compile(r"\b(?:summarize|summary|overview|key\s+takeaways|briefly\s+describe)\b", re.IGNORECASE)
    ]

    QUIZ_PATTERNS = [
        re.compile(r"\b(?:quiz\s+me|test\s+me|practice\s+questions|exam\s+questions|generate\s+a\s+quiz)\b", re.IGNORECASE)
    ]

    COMPARISON_PATTERNS = [
        re.compile(r"\b(?:compare|difference\s+between|versus|vs\.?|contrast)\b", re.IGNORECASE)
    ]

    PROBLEM_SOLVING_PATTERNS = [
        re.compile(r"\b(?:solve|calculate|compute|evaluate\s+the\s+integral|find\s+the\s+value|derive)\b", re.IGNORECASE)
    ]

    @classmethod
    def analyze_intent_and_metadata(
        cls,
        raw_query: str,
        normalized_query: str,
        resolved_query: str,
        language: str,
        is_follow_up: bool = False
    ) -> QueryMetadata:
        cleaned = resolved_query.strip().lower()

        # 1. Intent Detection
        if any(pat.search(cleaned) for pat in cls.CASUAL_PATTERNS) and len(cleaned.split()) <= 4:
            intent = "CASUAL"
        elif any(pat.search(cleaned) for pat in cls.SUMMARY_PATTERNS):
            intent = "SUMMARY"
        elif any(pat.search(cleaned) for pat in cls.QUIZ_PATTERNS):
            intent = "QUIZ"
        elif any(pat.search(cleaned) for pat in cls.COMPARISON_PATTERNS):
            intent = "COMPARISON"
        elif any(pat.search(cleaned) for pat in cls.PROBLEM_SOLVING_PATTERNS):
            intent = "PROBLEM_SOLVING"
        elif is_follow_up:
            intent = "FOLLOW_UP"
        elif any(w in cleaned for w in ["explain", "teach", "how does", "why does", "deep dive"]):
            intent = "EXPLANATION"
        else:
            intent = "DOCUMENT_QA"

        # 2. Entity & Concept Extraction
        raw_entities = re.findall(r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\b", resolved_query)
        action_verbs = {"Compare", "Explain", "Analyze", "Describe", "Define", "Discuss", "Show", "What", "How", "Why", "Tell"}
        cleaned_entities = []
        for ent in raw_entities:
            words = ent.split()
            if words and words[0] in action_verbs and len(words) > 1:
                cleaned_entities.append(" ".join(words[1:]))
            elif words and words[0] not in action_verbs:
                cleaned_entities.append(ent)
            for w in words:
                if len(w) > 3 and w not in action_verbs:
                    cleaned_entities.append(w)

        math_terms = re.findall(r"\b(?:matrix|vector|derivative|gradient|integral|algorithm|distribution|theorem|layer|regression)\b", resolved_query, re.IGNORECASE)
        all_entities = list(set([e.strip() for e in cleaned_entities if len(e.strip()) > 2] + [m.lower() for m in math_terms]))

        # 3. Learning Objective (Bloom's Taxonomy)
        if intent in ["DOCUMENT_QA", "CASUAL"]:
            objective = "recall"
        elif intent in ["EXPLANATION", "SUMMARY", "FOLLOW_UP"]:
            objective = "understand"
        elif intent in ["PROBLEM_SOLVING"]:
            objective = "apply"
        elif intent in ["COMPARISON"]:
            objective = "analyze"
        else:
            objective = "evaluate"

        # 4. Response Requirements
        needs_latex = bool(re.search(r"[∑∫√∂≤≥±=+\-*/^]|\b(?:formulas?|equations?|math|calculate|integral)\b", resolved_query, re.IGNORECASE))
        needs_table = bool(re.search(r"\b(?:table|comparison|tabular|columns|matrix)\b", resolved_query, re.IGNORECASE))
        needs_steps = intent in ["PROBLEM_SOLVING", "EXPLANATION", "COMPARISON"]

        # 5. Question Complexity
        if intent == "COMPARISON" or len(all_entities) >= 2:
            complexity = "comparative"
        elif intent in ["PROBLEM_SOLVING", "EXPLANATION"] and (needs_latex or len(resolved_query.split()) > 15):
            complexity = "multi_hop"
        else:
            complexity = "simple"

        return QueryMetadata(
            raw_query=raw_query,
            language=language,
            normalized_query=normalized_query,
            resolved_query=resolved_query,
            intent=intent,
            extracted_entities=all_entities[:10],
            learning_objective=objective,
            difficulty_level="Intermediate",
            response_requirements={
                "needs_latex": needs_latex,
                "needs_table": needs_table,
                "needs_steps": needs_steps,
                "needs_socratic": True,
            },
            question_complexity=complexity,
        )
