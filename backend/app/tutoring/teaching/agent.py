"""
TeachingAgent
=============

Adaptive Socratic Teaching Agent: synthesizes pedagogically tailored,
mathematically clean, and rigorously grounded explanations from a ContextBundle.
Powered by live multi-provider LLMs (Gemini, OpenAI, Groq, Azure) with high
temperature (0.8) for varied, natural, and creative tutoring responses.

Key Capabilities:
1. Dynamic Response Adaptation:
   - Topic / Syllabus / Roadmap queries -> Structured curriculum breakdown.
   - Conceptual questions -> Plain-language explanation + real-world analogy.
   - Comparison queries -> Markdown comparison table with tradeoffs.
   - Mathematical / derivation queries -> Clean LaTeX formatting ($...$, $$...$$).
2. Strict Out-of-Material Guardrail:
   - Declines questions completely outside the scope of the study material.
3. LaTeX Math Standards:
   - Pure math only inside LaTeX blocks. Never wrap English prose in math delimiters.
4. No Page Numbers:
   - Absolutely zero mentions of page numbers.
"""

import re
import time
import logging
from pathlib import Path
from typing import Generator, List, Optional, Tuple, Dict, Any

from app.schemas.tutoring import ContextBundle, TeachingResponse, QueryMetadata
from app.core.config import settings
from app.services.llm_service import default_llm_service

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Adaptive Teaching Prompt Contract
# ---------------------------------------------------------------------------

_RESPONSE_CONTRACT = """You are DeepTutor, an elite Socratic AI Professor and Academic Tutor.
Your goal is to deliver an intuitive, engaging, beautifully formatted, and rigorously grounded learning experience for students.

=== ADAPTIVE STUDENT-CENTRIC THINKING ===
Before answering, analyze the student's question intent and choose the optimal pedagogical format:

1. DEFINITION & QUICK CONCEPT (e.g. "what is X", "define X", "explain X in simple terms"):
   - Structure:
     * One clear, bold definition sentence right at the start.
     * A vivid, relatable real-world analogy (mental anchor).
     * 3-4 bullet points highlighting the core mechanisms or properties.
     * End with an Interactive Checkpoint active recall question.

2. COMPARISON & TRADEOFFS (e.g. "compare X and Y", "difference between X and Y", "X vs Y"):
   - Structure:
     * Executive Summary: 1-2 sentences capturing the essential philosophical difference.
     * Markdown Comparison Table: Columns: `Dimension | [Concept X] | [Concept Y]`. Include 4-5 key dimensions (e.g. Complexity, Linearity, Speed, Best Use Case).
     * Practical Decision Rule: "When to choose X vs when to choose Y".
     * End with an Interactive Checkpoint scenario question.

3. MECHANISM & STEP-BY-STEP (e.g. "how does X work", "what is the process of X"):
   - Structure:
     * High-Level Mental Model: 1-2 sentence overview of the mechanism.
     * Step-by-Step Flow: Numbered phases (`#### Step 1: ...`, `#### Step 2: ...`) explaining what happens at each stage.
     * Mathematical Formula or Flow Summary (clean LaTeX).
     * End with an Interactive Checkpoint trace question.

4. NUMERICAL & MATHEMATICAL DERIVATION (e.g. "derive X", "calculate X", "math behind X"):
   - Structure:
     * Given & Objective: Clear problem setup.
     * Mathematical Walkthrough: Step-by-step reasoning with clean LaTeX formatting ($...$ inline, $$...$$ display).
     * Final Result Box / Takeaway.
     * End with an Interactive Checkpoint question testing an edge case.

5. PRACTICE & EXAM QUESTIONS (e.g. "give me questions", "5 questions on this", "practice questions", "only need questions"):
   - High-yield, exam-grade inquiry based strictly on the study material.
   - USER FORMAT RESPECT:
     * If the student asks for "only questions", "just questions", or wants to test themselves:
       Present ONLY the clean numbered questions with clear problem descriptions and scenarios.
       DO NOT include answers, solution keys, or hints! Let the student work through them first.
     * If the student asks for questions with solutions or answers:
       Include the model answer and reasoning beneath each question.
     * If question count is requested, output exactly that many numbered questions.

6. TABLE PROBLEM SOLVING (e.g. "solve the table", "solve the table in page 22", "table 1.2"):
   - Structure:
     * Table Identification: Identify the table from the verified context excerpts or tables.
     * Method & Formula: State the formula or principle (e.g. arithmetic sequence common difference $d = x_2 - x_1$, divisibility rule, etc.).
     * Step-by-Step Walkthrough: Calculate each row/cell systematically.
     * Complete Solved Table: Render the ENTIRE, fully solved/filled Markdown table.

=== MULTI-TURN CONVERSATION MEMORY ===
- You have full access to the previous conversation history in this study session.
- If the student asks about something you explained earlier, or asks a follow-up referencing ANY prior response, answer, or question, refer accurately and coherently to what you previously taught or answered in this session.

=== CRITICAL MARKDOWN & TYPOGRAPHY CONSTRAINTS ===
- NO MONOLITHIC WALLS OF TEXT: Keep paragraphs short (maximum 2-3 sentences per paragraph).
- ALWAYS leave an empty line (double newline) before and after headers (`###`), horizontal dividers (`---`), and bullet lists (`*`).
- Bold key terms to make the explanation immediately scannable.
- Do NOT output any raw HTML tags (never use `<br>`, `<p>`, or `<div>`). Use native Markdown newlines and formatting only.
- Do NOT output ASCII-art diagrams or pseudo-code text boxes.
- Standard LaTeX syntax:
  - Inline math: `$variable$` or `$x + y$` for single variables, symbols, and inline formulas (e.g., `$Q$`, `$K$`, `$V$`, `$d_k$`).
  - Display block math: `$$ formula $$` on standalone lines for display equations.
  - CRITICAL: NEVER put plain English sentences or labels inside `$ ... $` or `$$ ... $$` unless enclosed in `\\text{...}`.

=== STRICT OUT-OF-MATERIAL GUARDRAIL ===
- You are strictly a tutor for the student's uploaded study material and its academic domain.
- If the student's question is COMPLETELY UNRELATED to the provided study material and cannot be grounded in it:
  Do NOT answer or hallucinate out-of-scope content.
  Politely decline with:
  "I am your dedicated tutor for this study material. Your question is outside the scope of your uploaded document on **[Topic / Subject]**. To keep your learning focused and productive, please ask questions related to this study material, or upload documents for that subject!"

=== CITATION & PAGE NUMBER RULES ===
- Ground all facts strictly in the verified context excerpts provided.
- Do NOT add citation footnotes or say "as seen on Page 5", but you may address the student's referenced page or table naturally.

=== INTERACTIVE CHECKPOINT ===
- For conceptual explanations or lectures, end your response with:
  ### 💡 Interactive Checkpoint
  **Active Recall Question**: exactly ONE thought-provoking question that ends in a question mark (`?`).
  Never append a "Hint:" line after the question mark.
- If the response is ALREADY a set of practice questions, an exam sheet, or a solved table, do NOT append an artificial Interactive Checkpoint; let the solution stand cleanly."""

_VISUAL_KEYWORDS = (
    "table", "diagram", "figure", "chart", "compare", "comparison",
    "flow", "structure", "vs ", "versus", "difference between",
)

_MIN_LIVE_RESPONSE_CHARS = 40


class TeachingAgent:
    """
    Socratic Teaching Agent:
    Transforms a ContextBundle into an adaptive, pedagogically tailored,
    and contract-compliant TeachingResponse.

    Every query goes through the LLM — no hardcoded topic summaries.
    """

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @classmethod
    def _clean_page_refs(cls, text: str) -> str:
        """Strip any page-number references from text while strictly preserving all newlines and markdown structure."""
        text = re.sub(r"\s*\(Page\s+\d+\)", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\bPage\s+\d+\b", "", text, flags=re.IGNORECASE)
        lines = [re.sub(r"[ \t]+", " ", ln).rstrip() for ln in text.split("\n")]
        return "\n".join(lines).strip()

    @classmethod
    def _sanitize_formula(cls, formula_str: str) -> str:
        """
        Sanitizes an extracted formula candidate string to prevent rendering raw
        English prose inside LaTeX $$...$$ blocks which squishes letters into unreadable math italics.
        """
        f = formula_str.strip()
        if not f:
            return ""

        # Strip outer $$ or $
        if f.startswith("$$") and f.endswith("$$"):
            f = f[2:-2].strip()
        elif f.startswith("$") and f.endswith("$"):
            f = f[1:-1].strip()

        # Count English prose words (>2 letters not in standard math/LaTeX commands)
        words = re.findall(r"\b[A-Za-z]{3,}\b", f)
        latex_commands = {
            "text", "frac", "sqrt", "sum", "prod", "max", "min", "log", "exp",
            "sin", "cos", "tan", "alpha", "beta", "gamma", "theta", "mathbf",
            "mathbb", "mathrm", "cdot", "times", "left", "right", "partial",
            "int", "infty", "approx", "equiv", "nabla", "forall", "exists"
        }
        prose_words = [w for w in words if w.lower() not in latex_commands]

        # If there are 4 or more prose words, it's a descriptive sentence, not a pure formula
        if len(prose_words) >= 4:
            if ":" in f:
                parts = f.split(":", 1)
                label = parts[0].strip()
                math_part = parts[1].strip()
                sub_prose = [w for w in re.findall(r"\b[A-Za-z]{3,}\b", math_part) if w.lower() not in latex_commands]
                if len(sub_prose) <= 2 and ("=" in math_part or "\\" in math_part):
                    return f"**{label}**:\n$$\n{math_part}\n$$"
            return f"**Note**: {f}"

        return f"$$\n{f}\n$$"

    @classmethod
    def _wants_visual(cls, query: str, context_bundle: ContextBundle) -> bool:
        q_lower = query.lower()
        if any(k in q_lower for k in _VISUAL_KEYWORDS):
            return True
        return bool(context_bundle.related_tables)

    @classmethod
    def _clean_topic_title(cls, topic_title: Optional[str]) -> str:
        if not topic_title:
            return "this concept"
        raw = str(topic_title).strip()
        has_path_separators = "\\" in raw or "/" in raw
        has_drive_letter = len(raw) > 2 and raw[1] == ":" and raw[0].isalpha()
        has_file_extension = any(
            raw.lower().endswith(ext)
            for ext in [".pmd", ".pdf", ".indd", ".doc", ".docx", ".txt", ".qxd", ".tex"]
        )

        if has_path_separators or has_drive_letter or has_file_extension:
            stem = Path(raw).stem
            if stem and len(stem) > 2 and not any(stem.lower().endswith(ext) for ext in [".pmd", ".pdf"]):
                cleaned = stem.replace("-", " ").replace("_", " ").strip()
                if cleaned.lower() not in ["prelims", "final", "untitled", "document", "cover", "final prelims"]:
                    return cleaned.title()
            return "this concept"

        if raw.lower() in ["academic studies", "subject lesson", "document overview", "prelims", "final prelims"]:
            return "this concept"
        return raw

    @classmethod
    def _default_follow_up(cls, topic_title: str) -> str:
        clean = cls._clean_topic_title(topic_title)
        return f"In your own words, why does {clean} work the way it does?"

    # ------------------------------------------------------------------
    # Prompt Construction
    # ------------------------------------------------------------------

    @classmethod
    def _build_prompts(
        cls, query_meta: QueryMetadata, context_bundle: ContextBundle
    ) -> Tuple[str, str]:
        """
        Constructs system + user prompts for the live LLM.
        The user prompt includes the full retrieved context so the model
        answers strictly from the database content with adaptive formatting.
        """
        system_prompt = (
            f"{_RESPONSE_CONTRACT}\n\n"
            "IMPORTANT: Base your entire response on the VERIFIED STUDY CONTEXT provided below. "
            "Think dynamically about the best format for the student's question. "
            "Do not restate the contract rules or internal instructions in your output."
        )

        # Build context from retrieved chunks (up to 6 for richer grounding)
        chunks_text: List[str] = []
        for i, chunk in enumerate(context_bundle.retrieved_chunks[:6], 1):
            sec = f" (Section: {chunk.chapter_section})" if chunk.chapter_section else ""
            content = cls._clean_page_refs(chunk.content.strip())
            chunks_text.append(f"--- Document Excerpt {i}{sec} ---\n{content}")

        context_str = (
            "\n\n".join(chunks_text)
            if chunks_text
            else "No specific study excerpts were retrieved for this query."
        )

        clean_formulas = []
        if context_bundle.related_formulas:
            for f in context_bundle.related_formulas[:3]:
                sanitized = cls._sanitize_formula(f)
                if sanitized:
                    clean_formulas.append(f"- {sanitized}")
        formulas_str = (
            "\nRelevant Formulas / Equations in Document:\n" + "\n".join(clean_formulas)
            if clean_formulas
            else ""
        )

        tables_str = ""
        if context_bundle.related_tables:
            tables_str = "\nRelevant Data Tables in Document:\n" + "\n".join(
                context_bundle.related_tables[:2]
            )

        wants_visual = cls._wants_visual(query_meta.resolved_query, context_bundle)

        history_lines = []
        if context_bundle.conversation_history:
            for turn in context_bundle.conversation_history:
                role = "Student" if turn.get("role") == "user" else "Assistant (You)"
                text = (turn.get("content") or turn.get("text") or "").strip()
                if text:
                    snip = text if len(text) <= 650 else text[:650] + "..."
                    history_lines.append(f"{role}: {snip}")

        history_str = (
            "=== FULL DIALOGUE HISTORY IN THIS STUDY SESSION ===\n"
            + "\n".join(history_lines)
            + "\n===================================================\n\n"
            if history_lines
            else ""
        )

        count_str = f"Requested Question Count: {query_meta.question_count}\n" if query_meta.question_count else ""
        topic_spec_str = f"Specific Target Topic: {query_meta.target_topic}\n" if query_meta.target_topic else ""

        # Format directives check
        format_dirs = query_meta.format_directives or {}
        is_questions_only = bool(format_dirs.get("questions_only", False))
        target_count = query_meta.question_count or 5
        effective_concept = query_meta.target_topic or context_bundle.topic_title or "this subject"

        # Table solving instruction
        is_solve_table = bool(format_dirs.get("solve_table")) or bool(query_meta.referenced_table) or (
            "table" in query_meta.resolved_query.lower()
            and any(w in query_meta.resolved_query.lower() for w in ["solve", "fill", "calculate", "complete", "check"])
        )

        if is_solve_table:
            ref_spec = f"'{query_meta.referenced_table}'" if query_meta.referenced_table else "the table"
            page_spec = f"on page {query_meta.referenced_page}" if query_meta.referenced_page else ""
            task_instruction = (
                f"3. TABLE SOLVING REQUEST: The student is asking to solve/complete {ref_spec} {page_spec}. "
                f"Check the VERIFIED STUDY CONTEXT excerpts and tables above. "
                f"If the table or its sequence data appears in the context: "
                f"(a) State clearly what the table asks to do. "
                f"(b) Explain the step-by-step mathematical method or formulas used to check/solve each entry (e.g. arithmetic sequence formula, difference test). "
                f"(c) Present the COMPLETE solved table in clean, valid Markdown with all columns filled and verified. "
                f"If the specific table is NOT found in the provided context excerpts, politely state that the table was not found on that page in the uploaded document and summarize what is there.\n"
            )
        elif is_questions_only or query_meta.intent == "PRACTICE_QUESTIONS":
            if is_questions_only:
                task_instruction = (
                    f"3. PRACTICE QUESTIONS (QUESTIONS ONLY): The student explicitly requested ONLY questions (no answers, no solution keys, no hints). "
                    f"Generate EXACTLY {target_count} rigorous, numbered exam preparation questions on {effective_concept}. "
                    f"Provide clear, numbered questions with real academic substance so the student can solve them. "
                    f"DO NOT include answers, solution keys, hints, or options. DO NOT output a multiple-choice quiz or code boxes.\n"
                )
            else:
                task_instruction = (
                    f"3. PRACTICE QUESTIONS: Generate EXACTLY {target_count} high-yield exam preparation questions on {effective_concept}. "
                    f"Number them cleanly (Question 1, Question 2, ...). "
                    f"If the student requested explanations or answers, provide clear explanations. DO NOT output an interactive multiple-choice quiz.\n"
                )
        else:
            task_instruction = ""

        user_prompt = (
            f"Subject Focus / Document Title: {context_bundle.topic_title or 'Academic Studies'}\n"
            f"Student Question: \"{query_meta.resolved_query}\"\n"
            f"Learning Intent: {query_meta.intent}\n"
            f"{count_str}"
            f"{topic_spec_str}"
            f"Visual aid requested/warranted: {'yes' if wants_visual else 'no'}\n\n"
            f"{history_str}"
            f"=== VERIFIED STUDY CONTEXT (from the student's uploaded document) ===\n"
            f"{context_str}\n"
            f"{formulas_str}\n"
            f"{tables_str}\n"
            f"======================================================================\n\n"
            f"Instructions:\n"
            f"1. Check if the question is within the scope of this study material. If completely unrelated, apply the Out-of-Material Guardrail and decline politely.\n"
            f"2. Check DIALOGUE HISTORY: If the student asks about ANY of your previous responses or explanations in this session, answer directly and accurately referencing that prior response.\n"
            f"{task_instruction}"
            f"4. Adapt your response format to the query intent (e.g. roadmap for 'main topics', intuitive explanation with analogy for 'explain', table for comparisons, clean LaTeX for math).\n"
            f"5. Do NOT output raw HTML (<br>) or ASCII-art. Use native Markdown only.\n"
            f"6. End with an Interactive Checkpoint active recall question ending in a question mark (?) ONLY for conceptual explanations or lectures. If this response is already a list of practice questions, an exam sheet, or a solved table, do NOT append an Interactive Checkpoint.\n"
            f"Teach the student now:"
        )

        return system_prompt, user_prompt

    # ------------------------------------------------------------------
    # Contract Enforcement
    # ------------------------------------------------------------------

    _STRIP_MENU_PATTERN = re.compile(
        r"(?i)(?:would you like to|where should we go next|next steps\??|options:).*?(?:\n\s*[-*0-9]+[.)]\s+.*)+",
        re.DOTALL,
    )

    @classmethod
    def _enforce_response_contract(
        cls, content: str, topic_title: str, query_meta: Optional[QueryMetadata] = None
    ) -> str:
        """
        Guarantees clean formatting:
        1. Converts raw HTML breaks (<br>, <br/>, <br />) into Markdown newlines.
        2. Strips page numbers.
        3. Strips multi-branch menu patterns.
        4. Strips trailing "Hint: ..." lines so response ends with a real question.
        5. Guarantees the response ends in exactly one question mark ('?').
        """
        content = content.strip()

        # 1. Convert raw HTML breaks into Markdown newlines
        content = re.sub(r"(?i)<br\s*/?>", "\n\n", content)

        # 2. Strip any residual page number references from LLM output while preserving newlines
        content = cls._clean_page_refs(content)

        # 3. Cut off any "How would you like to proceed" menus
        menu_pattern = re.compile(
            r"(?im)^\s*#{0,3}\s*(how (would|do) you (like|want) to proceed|"
            r"what would you like to do next)\b.*$"
        )
        match = menu_pattern.search(content)
        if match:
            content = content[: match.start()].rstrip()

        # If the response is an out-of-scope refusal, preserve refusal message
        if "outside the scope of your uploaded" in content.lower():
            return content

        # 4. Normalize Markdown spacing so elements render distinctly
        # Separate inline dividers if squished into text, without touching table delimiters like :---
        content = re.sub(r"(?<=\S)\s+---\s+(?=\S)", "\n\n---\n\n", content)
        # Ensure standalone dividers on their own line have clean empty lines
        content = re.sub(r"(?m)^[ \t]*-{3,}[ \t]*$", "\n---\n", content)
        # Ensure Markdown headers (##, ###, ####) have empty lines before them
        content = re.sub(r"(?<=\S)\n(#{1,4}\s+)", r"\n\n\1", content)
        # 3. Strip multi-branch navigation menus
        content = _STRIP_MENU_PATTERN.sub("", content)

        # 4. Strip trailing "Hint: ..." lines so response ends naturally
        lines = content.split("\n")
        while lines:
            last = lines[-1].strip().lower()
            if not last:
                lines.pop()
            elif (
                last.startswith("hint:")
                or last.startswith("*hint:")
                or last.startswith("_hint:")
                or last.startswith("*hint")
                or last.startswith("hint ")
            ):
                lines.pop()
            else:
                break
        content = "\n".join(lines).strip()

        # If this is practice questions, student requested only questions, or table solving, do not append artificial checkpoint
        is_exempt = query_meta and (
            query_meta.intent == "PRACTICE_QUESTIONS"
            or (query_meta.format_directives and query_meta.format_directives.get("questions_only"))
            or (query_meta.format_directives and query_meta.format_directives.get("solve_table"))
            or query_meta.referenced_table is not None
        )
        if is_exempt:
            return content

        # 5. Ensure Interactive Checkpoint exists for teaching explanations
        if "### 💡 Interactive Checkpoint" not in content and not content.endswith("?"):
            content += (
                f"\n\n### 💡 Interactive Checkpoint\n"
                f"**Active Recall Question**: {cls._default_follow_up(topic_title)}"
            )
        else:
            # Ensure it is cleanly separated with double newlines
            content = re.sub(r"(?<!\n\n)###\s*💡\s*Interactive Checkpoint", "\n\n### 💡 Interactive Checkpoint", content)

        return content

    # ------------------------------------------------------------------
    # Context-grounded Fallback (zero hardcoded text, clean LaTeX)
    # ------------------------------------------------------------------

    @classmethod
    def _context_grounded_fallback(
        cls, query: str, topic_title: str, context_bundle: ContextBundle
    ) -> str:
        """
        Used only when the live LLM is unavailable or returns an empty response.
        Formats the retrieved chunks cleanly into an intuitive response.
        """
        chunks = context_bundle.retrieved_chunks
        q_lower = query.lower()
        is_topic_query = any(
            k in q_lower for k in ("main topic", "topics", "syllabus", "overview", "what is this", "roadmap")
        )

        sections: List[str] = [
            f"## 🎓 Study Material: {topic_title}",
        ]

        if is_topic_query and chunks:
            sections.append("### 📚 Core Topics & Modules in this Document")
            seen = set()
            for c in chunks:
                t = c.chapter_section or c.topic
                if t and t not in seen:
                    seen.add(t)
                    snip = cls._clean_page_refs(c.content.strip())
                    if len(snip) > 200:
                        snip = snip[:200].rsplit(" ", 1)[0] + "..."
                    sections.append(f"- **{t}**: {snip}")
            if not seen:
                for i, c in enumerate(chunks[:4], 1):
                    snip = cls._clean_page_refs(c.content.strip())
                    if len(snip) > 200:
                        snip = snip[:200].rsplit(" ", 1)[0] + "..."
                    sections.append(f"- **Topic {i}**: {snip}")
        elif chunks:
            sections.append("### 📖 Key Insights from Your Document")
            for c in chunks[:4]:
                snippet = cls._clean_page_refs(c.content.strip())
                if len(snippet) > 400:
                    snippet = snippet[:400].rsplit(" ", 1)[0] + "…"
                sec = c.chapter_section or c.topic or ""
                header = f"**{sec}**" if sec else "**Excerpt**"
                sections.append(f"> {header}\n> {snippet}")

            if context_bundle.related_formulas:
                clean_f = [cls._sanitize_formula(f) for f in context_bundle.related_formulas[:3]]
                clean_f = [f for f in clean_f if f]
                if clean_f:
                    sections.append("### 📐 Key Formulations")
                    for f in clean_f:
                        sections.append(f)
        else:
            sections.append(
                "No relevant excerpts were found in your document for this question. "
                "Try rephrasing or uploading more source material."
            )

        sections.append(
            f"### 💡 Interactive Checkpoint\n"
            f"**Active Recall Question**: {cls._default_follow_up(topic_title)}"
        )

        return "\n\n".join(s for s in sections if s.strip())

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @classmethod
    def generate_teaching_response(
        cls, query_meta: QueryMetadata, context_bundle: ContextBundle
    ) -> TeachingResponse:
        """
        Every query is processed by the configured live LLM using the retrieved
        ContextBundle. Adapts dynamically to query intent and enforces out-of-scope guardrail.
        """
        query = query_meta.resolved_query
        topic_title = cls._clean_topic_title(context_bundle.topic_title)
        question_subject = topic_title if topic_title != "this concept" else "this concept"

        system_prompt, user_prompt = cls._build_prompts(query_meta, context_bundle)

        if default_llm_service.is_live_model_configured():
            try:
                llm_content = default_llm_service.generate(
                    prompt=user_prompt, system_prompt=system_prompt
                )
                if llm_content and len(llm_content.strip()) > _MIN_LIVE_RESPONSE_CHARS:
                    content = cls._enforce_response_contract(llm_content.strip(), topic_title, query_meta)
                    is_refusal = "outside the scope of your uploaded" in content.lower()
                    return TeachingResponse(
                        content=content,
                        intent=query_meta.intent,
                        citations=[] if is_refusal else context_bundle.citations,
                        grounding_score=0.3 if is_refusal else 0.98,
                        socratic_follow_up="" if is_refusal else cls._default_follow_up(topic_title),
                        suggested_questions=[] if is_refusal else [
                            f"How does {question_subject} apply to practical problems?",
                            "What are the key mechanisms and assumptions?",
                            "Can you walk me through a worked example?",
                        ],
                    )
                logger.warning(
                    "LLM returned empty/short response; falling back to context-grounded excerpt."
                )
            except Exception as e:
                logger.error(
                    f"Live LLM generation failed: {e}. "
                    "Falling back to context-grounded excerpt."
                )

        # Fallback: format retrieved chunks directly (clean LaTeX, no hardcoded text)
        content = cls._context_grounded_fallback(query, topic_title, context_bundle)
        return TeachingResponse(
            content=content,
            intent=query_meta.intent,
            citations=context_bundle.citations,
            grounding_score=0.75,
            socratic_follow_up=cls._default_follow_up(topic_title),
            suggested_questions=[
                "Can you explain this concept in a different way?",
                "What are the main differences vs. alternative approaches?",
                "How does this connect to other topics in the document?",
            ],
        )

    @classmethod
    def stream_teaching_tokens(
        cls, query_meta: QueryMetadata, context_bundle: ContextBundle
    ) -> Generator[str, None, None]:
        """
        Streams response tokens via SSE.
        Uses live-model token stream when configured; falls back to
        context-grounded excerpt stream.
        """
        query = query_meta.resolved_query
        topic_title = cls._clean_topic_title(context_bundle.topic_title)
        system_prompt, user_prompt = cls._build_prompts(query_meta, context_bundle)

        if default_llm_service.is_live_model_configured():
            try:
                yielded_any = False
                for token in default_llm_service.stream_generate(
                    prompt=user_prompt, system_prompt=system_prompt
                ):
                    yield token
                    yielded_any = True
                if yielded_any:
                    return
                logger.warning("LLM stream yielded nothing; falling back to context excerpts.")
            except Exception as e:
                logger.error(f"Live LLM token streaming failed: {e}. Falling back to excerpts.")

        # Fallback: stream the context-grounded excerpt word by word
        response_text = cls._context_grounded_fallback(query, topic_title, context_bundle)
        words = response_text.split(" ")
        for i, word in enumerate(words):
            yield word if i == 0 else " " + word
            time.sleep(0.005)

    @classmethod
    def generate_flashcards_or_quiz(
        cls,
        topic: str,
        retrieved_chunks: List[Dict[str, Any]],
        question_count: int = 5,
        mode: str = "quiz"
    ):
        """
        Self-contained flashcard/quiz capability callable by the teaching agent.
        """
        from app.tutoring.flashcards.generator import FlashcardQuizGenerator
        return FlashcardQuizGenerator.generate(
            topic=topic,
            retrieved_chunks=retrieved_chunks,
            question_count=question_count,
            mode=mode
        )
