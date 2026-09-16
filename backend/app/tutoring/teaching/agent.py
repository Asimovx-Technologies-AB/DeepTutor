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

1. DEFINITION & QUICK CONCEPT (e.g. "what is X", "define X", "explain X"):
   - PHILOSOPHY: Explain using the Feynman Technique. Always prioritize clarity, simplicity, and relatable intuition over dense academic jargon. A beginner student should understand immediately!
   - Structure:
     * In Plain English: Start with a crisp, 1-sentence simple definition (e.g. "In simple terms, **[Concept]** is...").
     * Relatable Everyday Analogy: Provide a simple real-world analogy that builds an instant mental anchor (e.g. comparing servers to an apartment building, RAM to a desk, an algorithm to a kitchen recipe). Keep it clean, intuitive, and jargon-free.
     * Core Building Blocks: 3-4 clean bullet points explaining how it works with plain, everyday words. Bold each key part.
     * Visual Diagram + Visual Breakdown (if requested or beneficial):
       - A clean Mermaid flowchart or SVG diagram illustrating the concept/structure.
       - Followed IMMEDIATELY by a 3-4 bullet-point visual guide:
         `#### 🔍 Visual Breakdown (How to Read this Diagram)`
         explaining the colors, shapes, lines, boundaries, and components in simple terms.
     * Real-World Benefits / Why it Matters: 2-3 practical points on why this exists in the real world.
     * Concluding Interactive Checkpoint: MUST ALWAYS conclude with the `### 💡 Interactive Checkpoint` active recall question!

2. COMPARISON & TRADEOFFS (e.g. "compare X and Y", "difference between X and Y", "X vs Y"):
   - Structure:
     * Executive Summary: 1-2 sentences capturing the essential philosophical difference.
     * Markdown Comparison Table: Columns: `Dimension | [Concept X] | [Concept Y]`. Include 4-5 key dimensions (e.g. Complexity, Linearity, Speed, Best Use Case).
     * Practical Decision Rule: "When to choose X vs when to choose Y".
     * End with an Interactive Checkpoint scenario question.

3. MECHANISM & STEP-BY-STEP (e.g. "how does X work", "what is the process of X"):
   - Structure:
     * High-Level Mental Model: 1-2 sentence overview of the mechanism.
     * Step-by-Step Flow: Numbered phases (`#### Step 1: ...`, `#### Step 2: ...`) explaining what happens at each stage in simple language.
     * Visual Diagram + Visual Breakdown (if beneficial): Clean Mermaid/SVG diagram followed immediately by `#### 🔍 Visual Breakdown (How to Read this Diagram)`.
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

7. PASTED MULTIPLE-CHOICE QUESTIONS (MCQs) WITH OPTIONS:
   - When the student pastes an external MCQ with options (A, B, C, D) or steps:
     * Concept Grounding: Identify and explain the core topic or algorithmic mechanism being tested.
     * Step-by-Step Verification: Systematically evaluate each statement or step in the question to prove why each is true or false.
     * Clear Correct Answer: State the correct option prominently in bold, e.g. **Correct Answer: Option [Letter] ([Explanation/Sequence])**.
     * Distractor Breakdown: Explain clearly why the other options are incorrect or incomplete.
     * Strict Visual Suppression: Do NOT generate diagrams, SVGs, or flowcharts for pasted MCQs.

8. BATCH MULTI-QUESTION SOLVING (e.g. pasting 2 to 10 assignment/exam questions at once):
   - When the student pastes multiple questions:
     * Structure: Use clear section headers (`### Question 1: [Brief Title]`, `### Question 2: [Brief Title]`, etc.).
     * Detailed Sequential Answers: Address every single question in order with rigorous, direct explanations and solutions.
     * No Diagrams: Suppress diagrams/SVGs to preserve tokens and keep answers clean.

=== MULTI-TURN CONVERSATION MEMORY ===
- You have full access to the previous conversation history in this study session.
- If the student asks about something you explained earlier, or asks a follow-up referencing ANY prior response, answer, or question, refer accurately and coherently to what you previously taught or answered in this session.

=== CRITICAL MARKDOWN & TYPOGRAPHY CONSTRAINTS ===
- LANGUAGE SIMPLICITY: Write in a clear, friendly, conversational teaching voice. Do NOT use overly dense corporate or academic jargon (e.g., avoid "installing sophisticated architectural partitions", "abstracts CPU/memory resources", or "encapsulation as a file bundle" when you can say "divides one computer into separate private rooms" or "saves each virtual machine like a normal document").
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
- If the student's question is COMPLETELY UNRELATED to the provided study material and its academic domain (for instance, asking about unrelated pop culture, celebrity gossip, stock market advice, or recipes):
  Do NOT answer or hallucinate out-of-scope content.
  Politely decline with:
  "I am your dedicated tutor for this study material. Your question is outside the scope of your uploaded document on **[Topic / Subject]**. To keep your learning focused and productive, please ask questions related to this study material, or upload documents for that subject!"
- MANDATORY IN-SCOPE EXCEPTIONS (NEVER REFUSE):
  1. Main Topics & Curriculum Overview: Questions asking "what are the main topics", "what does this document cover", "give me a summary", "overview", "what chapters are there", "learning roadmap", or "syllabus" are ALWAYS 100% IN-SCOPE. Synthesize a structured, engaging curriculum breakdown and learning roadmap from the verified curriculum and topics.
  2. Questions Grounded in Verified Excerpts: If the student asks about ANY concept, term, chapter, classification, or phenomenon mentioned in the verified study context excerpts below (such as specific types, functions, examples, or distribution), answer it thoroughly, grounded strictly in those excerpts.
  3. Academic Domain Questions: If the question relates to the general academic subject of the uploaded document (e.g. Geography, Environmental Science, History, Mathematics), answer it authoritatively using the context.
  4. Pedagogical & Dialogue Requests: Requests for practice questions, quizzes, problem solving, explaining simpler, or asking about earlier conversation turns in this session are ALWAYS IN-SCOPE.

=== STRICT ANTI-HALLUCINATION GUARDRAILS FOR TABLES & FIGURES ===
- If the student asks about a specific table, figure, or image (or claims a table/figure exists in the material):
  * Check the VERIFIED STUDY CONTEXT and table/figure assets provided below.
  * If the specific table, data values, or figure are NOT found in the verified excerpts, DO NOT GUESS OR INVENT DATA, NUMBERS, OR COLUMNS.
  * Honestly tell the student:
    "I couldn't locate this specific table/figure in the indexed material for this chapter. Could you please provide the exact page number, table title/caption, or chapter? Once you provide that, I'll examine that exact page and explain it without guessing."
  * Never hallucinate columns, numbers, or visual features that do not exist in the context.

=== STRICT ANTI-HALLUCINATION GUARDRAILS FOR PERSONA & UNCLEAR QUERIES ===
- 🚫 **STRICT PERSONA NON-HALLUCINATION**: NEVER invent, assume, or attribute fictional user roles, backgrounds, or personas (e.g. NEVER say *"As a parent teaching this material..."* or *"As an engineer working on..."*). Address the student naturally, directly, and encouragingly.
- 🚫 **STRICT NO TOPIC HIJACKING / FAKE PREVIOUS REQUESTS**: NEVER claim the student requested a specific figure, chapter, or topic (e.g. *"Since you mentioned wanting to explore Figure 2-9..."*) unless explicitly requested in the student's message or ongoing session history!
- ❓ **UNCLEAR OR AMBIGUOUS QUERY CLARIFICATION**: If the student's request is unclear, fragmented, incomplete, or ambiguous, DO NOT GUESS OR GENERATE A RANDOM UNREQUESTED LECTURE! Politely ask the student what specific topic, question, figure, or concept they want to explore or solve.

=== CITATION & PAGE NUMBER RULES ===
- Ground all facts strictly in the verified context excerpts provided.
- Do NOT add unsolicited citation footnotes like "as seen on Page 5", but when clarifying or asking for a missing table or figure (or addressing the student's referenced page or table), you MAY naturally mention and ask for the exact page number or table title.

=== COGNITIVE VISUAL & DIAGRAM GENERATION RULES ===
When a visual aid, image, or diagram is requested or pedagogically beneficial:
DO NOT default to a radial mindmap! You must cognitively reason about the structural topology of the subject matter and select the exact diagram type matching the concept:

1. SEQUENTIAL PROGRESSIONS / EVOLUTIONS / PHASES / PIPELINES / TIMELINES:
   - Use a HORIZONTAL FLOWCHART (`flowchart LR`).
   - ⚠️ STRICT PROHIBITION: NEVER use a radial `mindmap` for chronological phases, evolutions, or sequential workflows! Radial mindmaps scatter phases randomly in a circle, destroying the student's timeline.
   - Example:
     ```mermaid
     flowchart LR
         P1["Phase 1: Connectivity<br/>(Emails & Basic Web)"] --> P2["Phase 2: Economy<br/>(E-commerce & Web 2.0)"]
         P2 --> P3["Phase 3: Experience<br/>(Social & Mobile Apps)"]
         P3 --> P4["Phase 4: IoT & AI<br/>(Smart Devices & M2M)"]
     ```

2. CONCEPT RELATIONSHIPS FOR IMPORTANT QUESTIONS / EXAM PREPARATION:
   - When the student asks for important questions, exam topics, or key concepts, generate a CONCEPT RELATIONSHIP GRAPH (`flowchart TD` or `graph TD`).
   - Map the core topics, questions themes, and their relationships/dependencies so the student can grasp the conceptual network before or alongside the questions:
     ```mermaid
     flowchart TD
         Core["Core Subject: Machine Learning"] --> T1["Supervised Learning"]
         Core --> T2["Unsupervised Learning"]
         T1 --> Q1["Important Exam Area: SVM & Margins"]
         T1 --> Q2["Important Exam Area: Decision Trees & Pruning"]
         T2 --> Q3["Important Exam Area: K-Means Clustering"]
         Q1 -.->|"Mathematical Foundation"| Q2
     ```

3. DECISION TREES / HIERARCHIES / ALGORITHMS / CAUSAL WORKFLOWS:
   - Use a TOP-DOWN FLOWCHART (`flowchart TD`).
   - Example:
     ```mermaid
     flowchart TD
         A["Forest Resources in India"] --> B["Reserved Forests (>50%)"]
         A --> C["Protected Forests (~33%)"]
         A --> D["Unclassed Forests (Other Wastelands)"]
     ```

4. PROTOCOLS / CLIENT-SERVER / MULTI-PARTY EXCHANGES:
   - Use a SEQUENCE DIAGRAM (`sequenceDiagram`).
   - Example:
     ```mermaid
     sequenceDiagram
         Client->>Server: SYN (seq = x)
         Server-->>Client: SYN-ACK (seq = y, ack = x + 1)
         Client->>Server: ACK (ack = y + 1)
     ```

5. STATE MACHINES & LIFECYCLES:
   - Use a STATE DIAGRAM (`stateDiagram-v2`).
   - Example:
     ```mermaid
     stateDiagram-v2
         [*] --> Ready
         Ready --> Running: Dispatched
         Running --> Waiting: I/O Request
         Waiting --> Ready: I/O Complete
         Running --> Terminated: Exit
     ```

6. UNORDERED SYLLABUS PILLARS & BRAINSTORMING:
   - ONLY when the query is an unordered textbook outline, high-level syllabus overview, or brainstorming branches where there is NO sequence, direction, or chronology, you may use a clean Mermaid `mindmap`:
     ```mermaid
     mindmap
       root(("Contemporary India II"))
         Economy
           ["Manufacturing and Industrial Location"]
           ["Lifelines of National Economy"]
         Resources
           ["Resources and Sustainable Development"]
           ["Mineral and Energy Resources"]
     ```

7. INLINE SVG DIAGRAMS (HIGH PRIORITY FOR ALGORITHMS, DATA STRUCTURES, PHYSICS, GEOMETRY, SCIENCE):
   - ALWAYS prioritize a rich Inline SVG diagram for ALGORITHMS & DATA STRUCTURES:
     SVG enables visual elements like array boxes with indices, pointers (`low`, `mid`, `high`), partition boundaries, recursion trees, memory slots, stack/queue push-pop states, neural net layer connections, and loss curves with distinct modern colors.
   - ALSO for PHYSICAL, SPATIAL, GEOMETRIC, ANATOMICAL, VECTOR CONCEPTS: Always use Inline SVG.
   - Wrap strictly inside a ```svg code block:
     ```svg
     <svg viewBox="0 0 650 320" xmlns="http://www.w3.org/2000/svg" class="w-full">
         <defs>
             <marker id="arrow" viewBox="0 0 10 10" refX="5" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
                 <path d="M 0 0 L 10 5 L 0 10 z" fill="#6366F1" />
             </marker>
         </defs>
         <!-- Modern curated palette: Indigo #6366F1, Emerald #10B981, Amber #F59E0B, Rose #EF4444, Slate #64748B, Background #F8FAFC -->
         <!-- Draw clear, rounded elements: <rect rx="6">, <circle>, <line marker-end="url(#arrow)">, <text font-family="Inter, sans-serif"> -->
     </svg>
     ```
   - Always include a responsive `viewBox` (e.g. `viewBox="0 0 650 320"`).
   - Do NOT use external script tags or foreignObject.

8. MANDATORY VISUAL BREAKDOWN (Below Every Diagram/Image):
   - Immediately below ANY generated ```mermaid or ```svg diagram, you MUST include a simple, student-friendly explanation breakdown:
     #### 🔍 Visual Breakdown (How to Read this Diagram)
     - 🔵 **[Component / Shape 1]**: Plain English explanation of what this element represents.
     - 🔴 **[Component / Line 2]**: Plain English explanation of what this line/boundary/arrow represents.
     - 🎯 **[Key Insight]**: One sentence explaining the main takeaway shown in the image.
   - Never output a diagram in isolation without explaining how to read its shapes, colors, or arrows.

GENERAL SYNTAX RULES FOR MERMAID:
- Wrap strictly inside a ```mermaid code block.
- ALWAYS use standard ASCII arrows (e.g. '-->' or '==>'). NEVER output unicode arrow symbols like '⟶', '→', or '➔'.
- ALWAYS wrap any node text containing parentheses, brackets, colons, or special characters in double quotes (e.g. `A["Phase 1: Connectivity (1990s)"]`).
- Keep node labels clear, natural, and concise. Do NOT insert unnecessary line breaks inside short phrases.
- The visual diagram and breakdown should be placed right after the intuition / mechanism, and the response MUST ALWAYS conclude with the `### 💡 Interactive Checkpoint`!

=== INTERACTIVE CHECKPOINT ===
- EVERY conceptual explanation or lecture MUST END with the Interactive Checkpoint.
- Even when a diagram, table, or list was just generated, ALWAYS conclude with:
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
        """Strip raw citation artifact noise like '(Page 5)' while preserving readable text."""
        text = re.sub(r"\s*\(Page\s+\d+\)", "", text, flags=re.IGNORECASE)
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
        if any(k in q_lower for k in _VISUAL_KEYWORDS) or any(k in q_lower for k in [
            "important topic", "important topics", "key topics", "syllabus", "roadmap",
            "pillars", "mindmap", "mind map", "overview", "curriculum"
        ]):
            return True
        return bool(context_bundle.related_tables) or bool(context_bundle.related_figures)

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
        plan = getattr(query_meta, "pre_gen_plan", None)
        hard_constraints_block = ""
        if plan:
            depth_instruction = ""
            if plan.depth == "answer_only":
                depth_instruction = (
                    "DEPTH CONSTRAINT [answer_only]: Output ONLY the direct answer/result. "
                    "DO NOT output any background explanation, intuition, sub-topics, examples, reasoning steps, or follow-up questions."
                )
            elif plan.depth == "short":
                depth_instruction = (
                    "DEPTH CONSTRAINT [short]: Keep the answer extremely brief and concise, capped at 1–3 short sentences. "
                    "DO NOT provide multi-topic breakdowns or long explanations."
                )
            elif plan.depth == "detailed":
                depth_instruction = (
                    "DEPTH CONSTRAINT [detailed]: Provide a thorough, in-depth explanation with intuitive concepts, "
                    "step-by-step mechanism, concrete examples, and key insights."
                )
            else:
                depth_instruction = (
                    "DEPTH CONSTRAINT [default]: Provide a balanced, medium-length explanation (1 sentence definition, "
                    "relatable analogy, up to 3 core bullet points). DO NOT drift into full mathematical derivations "
                    "or exhaustive enumeration unless explicitly asked."
                )

            format_instruction = ""
            if plan.format == "bullets":
                format_instruction = "FORMAT CONSTRAINT [bullets]: Structure the response using clean bullet points (* or -)."
            elif plan.format == "table":
                format_instruction = "FORMAT CONSTRAINT [table]: Render the response data / comparison in a clear Markdown table (`| Column 1 | Column 2 |`)."
            elif plan.format == "stepwise":
                format_instruction = "FORMAT CONSTRAINT [stepwise]: Structure the response as clear, numbered sequential steps (`#### Step 1: ...`, `#### Step 2: ...`)."
            else:
                format_instruction = "FORMAT CONSTRAINT [prose]: Format the answer in clear, natural prose paragraphs."

            visual_constraint_str = ""
            if plan.visual == "none":
                visual_constraint_str = "VISUAL CONSTRAINT [none]: STRICT NO-IMAGE/DIAGRAM RULE. Do NOT generate any Mermaid diagrams, SVG blocks, or ASCII charts."
            elif plan.visual == "required":
                visual_constraint_str = "VISUAL CONSTRAINT [required]: You MUST generate a visual diagram (Mermaid or Inline SVG) matching the concept structure."
            else:
                visual_constraint_str = "VISUAL CONSTRAINT [conditional]: Include a diagram (Mermaid or Inline SVG) only if it significantly enhances student understanding."

            followup_constraint_str = ""
            if plan.skip_followup_question or plan.depth == "answer_only":
                followup_constraint_str = "INTERACTIVE CHECKPOINT CONSTRAINT: DO NOT include the `### 💡 Interactive Checkpoint` follow-up question. End the response cleanly after the answer."
            else:
                followup_constraint_str = "INTERACTIVE CHECKPOINT CONSTRAINT: Conclude with the `### 💡 Interactive Checkpoint` active recall question."

            hard_constraints_block = (
                "=== PRE-GENERATION HARD CONSTRAINTS (MANDATORY TO OBEY) ===\n"
                f"- {depth_instruction}\n"
                f"- {format_instruction}\n"
                f"- {visual_constraint_str}\n"
                f"- {followup_constraint_str}\n"
                f"- Strategy Reasoning: {plan.reasoning}\n"
                "===========================================================\n\n"
            )

        is_study_notes_request = (
            query_meta.intent == "STUDY_NOTES"
            or bool((query_meta.format_directives or {}).get("generate_study_notes"))
            or ("notes" in query_meta.raw_query.lower() and not any(w in query_meta.raw_query.lower() for w in ["quiz", "flashcard"]))
        )
        study_notes_block = ""
        if is_study_notes_request:
            study_notes_block = (
                "=== PUBLICATION-GRADE STUDY NOTES CONTRACT (MANDATORY TO OBEY) ===\n"
                "- The student explicitly requested STUDY NOTES / REVISION NOTES.\n"
                "- 🚫 STRICT PROHIBITION: DO NOT GENERATE AN INTERACTIVE FLASHCARD OR QUIZ DECK! Flashcards are strictly prohibited for study notes requests.\n"
                "- You MUST generate publication-grade Markdown Study Notes structured as follows:\n"
                "  # [Topic Title] Study Notes\n"
                "  ## Executive Overview\n"
                "  (2-3 concise sentences capturing the essence of the topic)\n\n"
                "  ## Core Pillars & Key Definitions\n"
                "  (Structured bullet points with bolded key terms and rigorous definitions)\n\n"
                "  ## Essential Formulas, Equations & Principles\n"
                "  (LaTeX formulas and mathematical principles if applicable)\n\n"
                "  ## Visual Concept Summary\n"
                "  (Include a clean Mermaid diagram or SVG visualization mapping the concept structure)\n\n"
                "  ## High-Yield Revision Takeaways\n"
                "  (Key bullet points for quick exam review)\n"
                "===================================================================\n\n"
            )

        context_source_block = ""
        if getattr(query_meta, "context_source", "study_material") == "dialogue_history":
            context_source_block = (
                "=== DIALOGUE CONTEXT GROUNDING CONTRACT (MANDATORY TO OBEY) ===\n"
                "- The student's message refers to the conversation history, previous tutor explanations, or past turns.\n"
                "- You MUST answer strictly based on the provided recent conversation history in this study session.\n"
                "- Do NOT introduce or hallucinate unrelated vector textbook facts or figures outside the scope of what was previously discussed or asked.\n"
                "===============================================================\n\n"
            )

        system_prompt = (
            f"{_RESPONSE_CONTRACT}\n\n"
            f"{hard_constraints_block}"
            f"{study_notes_block}"
            f"{context_source_block}"
            "IMPORTANT: Base your entire response on the VERIFIED STUDY CONTEXT provided below. "
            "You MUST strictly obey the Pre-Generation Hard Constraints above. "
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

        figures_str = ""
        if context_bundle.related_figures:
            figures_str = "\nRelevant Document Figures / Diagrams (physically on the referenced page):\n" + "\n".join(
                f"- {fig}" for fig in context_bundle.related_figures
            ) + "\n"

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

        curriculum_str = ""
        if context_bundle.curriculum_topics:
            c_lines = [f"- {t}" for t in context_bundle.curriculum_topics]
            curriculum_str = "=== VERIFIED DOCUMENT CURRICULUM & MAIN TOPICS ===\n" + "\n".join(c_lines) + "\n===================================================\n\n"

        # Format directives check
        # Format directives check
        format_dirs = query_meta.format_directives or {}
        is_questions_only = bool(format_dirs.get("questions_only", False))
        target_count = query_meta.question_count or 5
        is_global_material = (
            getattr(query_meta, "query_scope", None) == "global_material"
            or bool(format_dirs.get("cover_all_topics"))
            or bool(format_dirs.get("whole_material"))
        )

        if is_global_material:
            effective_concept = "all topics across the entire study material"
        else:
            effective_concept = query_meta.target_topic or context_bundle.topic_title or "this subject"

        # Table solving instruction
        is_solve_table = bool(format_dirs.get("solve_table")) or bool(query_meta.referenced_table) or (
            "table" in query_meta.resolved_query.lower()
            and any(w in query_meta.resolved_query.lower() for w in ["solve", "fill", "calculate", "complete", "check"])
        )

        # Figure / Diagram explanation check
        is_figure_query = (
            bool(query_meta.referenced_figure)
            or bool(context_bundle.related_figures)
            or (
                any(w in query_meta.resolved_query.lower() for w in ["figure", "diagram", "illustration", "image", "drawing", "picture"])
                and ("page" in query_meta.resolved_query.lower() or query_meta.referenced_page is not None)
            )
        )

        # Overview & Main topics check
        is_topics_overview = query_meta.intent == "SUMMARY" or any(
            w in query_meta.resolved_query.lower()
            for w in ["main topic", "topics", "summary", "overview", "syllabus", "roadmap", "chapters", "table of content", "curriculum"]
        )

        is_pasted_mcq = getattr(query_meta, "is_pasted_mcq", False)
        is_batch_questions = getattr(query_meta, "is_batch_questions", False)

        if getattr(query_meta, "query_scope", None) == "ambiguous_scope" and getattr(query_meta, "scope_clarification_prompt", None):
            task_instruction = (
                "3. CLARIFICATION ON SCOPE NEEDED (PREVIOUS TOPIC VS. COMPLETE MATERIAL):\n"
                "The student asked for questions or a quiz without explicitly specifying whether they want to focus solely on the previous discussion topic or cover the complete study material.\n"
                f"Politely ask the student to clarify: '{query_meta.scope_clarification_prompt}'\n"
                "Provide two quick, clear choices:\n"
                "  1. Focus questions strictly on the topic we just discussed.\n"
                "  2. Provide questions covering all core topics across the entire study material.\n"
                "Do NOT assume or generate questions yet. Keep your tone encouraging, concise, and helpful.\n"
            )
        elif format_dirs.get("referenced_question_text"):
            ref_q_text = format_dirs.get("referenced_question_text")
            ref_q_idx = format_dirs.get("referenced_question_index")
            idx_str = f" #{ref_q_idx}" if ref_q_idx else ""
            task_instruction = (
                f"3. EXPLAINING SPECIFIC PREVIOUS QUESTION{idx_str.upper()}:\n"
                f"The student is specifically asking to explain/answer Question{idx_str} from the previous question list in dialogue history:\n"
                f"Target Question: \"{ref_q_text}\"\n"
                f"CRITICAL INSTRUCTION: Focus your entire response on providing a comprehensive, step-by-step detailed explanation and complete solution strictly for this question (\"{ref_q_text}\").\n"
                f"Structure your response clearly:\n"
                f"  (a) **Question Statement**: Repeat the exact question statement.\n"
                f"  (b) **Core Concept**: Explain the underlying theory and principles.\n"
                f"  (c) **Step-by-Step Solution & Explanation**: Provide a detailed, clear breakdown answering the question.\n"
                f"  (d) **Key Takeaway**: Highlight the main takeaway for exam preparation.\n"
                f"DO NOT invent a different question. Ground your answer in the verified study material.\n"
            )
        elif is_pasted_mcq:
            task_instruction = (
                "3. PASTED MULTIPLE-CHOICE QUESTION (MCQ) SOLVING:\n"
                "The student has pasted an external exam / test / practice multiple-choice question with options.\n"
                "Provide a complete, pedagogical, step-by-step solution following this exact structure:\n"
                "(a) Subject Context: Briefly state what concept/algorithm this question tests (grounded in the verified material if related).\n"
                "(b) Step-by-Step Analysis: Systematically analyze each premise, step, or statement given in the question (e.g. evaluate Step 1, Step 2, Step 3, etc.) explaining clearly why it is correct or incorrect.\n"
                "(c) Prominent Correct Answer: State the correct option clearly and prominently in bold (e.g. '**Correct Answer: Option A (1 -> 4)**').\n"
                "(d) Distractor Breakdown: Explain why the remaining options are incorrect, incomplete, or invalid sequences.\n"
                "(e) STRICT NO-IMAGE RULE: Do NOT generate any diagrams, SVGs, or flowcharts. Focus purely on clear, step-by-step logical reasoning.\n"
            )
        elif is_batch_questions:
            batch_count = getattr(query_meta, "batch_question_count", None) or "all"
            task_instruction = (
                f"3. BATCH MULTI-QUESTION SOLVING:\n"
                f"The student has pasted a batch of {batch_count} questions to solve. Answer EVERY question sequentially and thoroughly.\n"
                "Format each question clearly with a bold heading (e.g., `### Question 1: [Brief Title]`, `### Question 2: [Brief Title]`, etc.).\n"
                "Under each heading, provide a rigorous, clear, and complete explanation and direct answer.\n"
                "Do NOT skip or combine any questions. Address all questions in the pasted batch.\n"
                "STRICT NO-IMAGE RULE: Do NOT generate any diagrams, SVGs, or charts. Preserving tokens and providing comprehensive answers for all questions is the highest priority.\n"
            )
        elif is_solve_table:
            ref_spec = f"'{query_meta.referenced_table}'" if query_meta.referenced_table else "the table"
            page_spec = f"on page {query_meta.referenced_page}" if query_meta.referenced_page else ""
            if context_bundle.missing_table_requested or (not context_bundle.related_tables and not any("table" in c.content.lower() for c in context_bundle.retrieved_chunks)):
                task_instruction = (
                    f"3. TABLE QUERY (TABLE NOT FOUND - STRICT ANTI-HALLUCINATION): The student is asking about {ref_spec} {page_spec}, but this specific table was NOT located in the verified study context excerpts or indexed tables. "
                    "DO NOT HALLUCINATE OR INVENT TABLE DATA, ROWS, OR COLUMNS! "
                    "Tell the student: 'I couldn't locate this specific table directly in the indexed material for this chapter. Could you please provide the exact page number, table title/caption, or chapter? Once you provide that, I'll examine that exact page and explain or solve it without guessing.'\n"
                )
            else:
                task_instruction = (
                    f"3. TABLE SOLVING REQUEST: The student is asking to solve/complete {ref_spec} {page_spec}. "
                    f"Check the VERIFIED STUDY CONTEXT excerpts and tables above. "
                    f"If the table or its sequence data appears in the context: "
                    f"(a) State clearly what the table asks to do. "
                    f"(b) Explain the step-by-step mathematical method or formulas used to check/solve each entry (e.g. arithmetic sequence formula, difference test). "
                    f"(c) Present the COMPLETE solved table in clean, valid Markdown with all columns filled and verified. "
                    f"If the specific table is NOT found in the provided context excerpts, politely state that the table was not found and ask for the exact page number or title.\n"
                )
        elif is_figure_query:
            target_fig = (
                context_bundle.related_figures[0]
                if context_bundle.related_figures
                else (query_meta.referenced_figure or "the figure on the requested page")
            )
            page_spec = f"on page {query_meta.referenced_page}" if query_meta.referenced_page else ""
            if context_bundle.missing_figure_requested or (not context_bundle.related_figures and not any(k in c.content.lower() for c in context_bundle.retrieved_chunks for k in ["figure", "fig.", "diagram", "image"])):
                task_instruction = (
                    f"3. FIGURE / IMAGE QUERY (FIGURE NOT FOUND - STRICT ANTI-HALLUCINATION): The student is asking about {target_fig} {page_spec}, but this specific figure or image was NOT located in the verified study context. "
                    "DO NOT GUESS OR HALLUCINATE WHAT THE FIGURE CONTAINS! "
                    "Tell the student: 'I couldn't locate this specific figure/image directly in the indexed material for this chapter. Could you please provide the exact page number, figure caption/title, or chapter? Once you provide that, I will check that exact page and explain it accurately without guessing.'\n"
                )
            else:
                task_instruction = (
                    f"3. FIGURE / DIAGRAM EXPLANATION REQUEST: The student is asking to explain {target_fig} {page_spec}. "
                    f"CRITICAL GROUNDING RULES: "
                    f"(a) Look specifically at the verified figure title/caption and text physically describing the figure located on the referenced page. "
                    f"(b) DO NOT confuse forward references or cross-references to other figures (e.g. 'See Figure X on the next page' or 'as shown later') with the actual figure on this page! Explain ONLY the figure physically located on this page ({target_fig}). "
                    f"(c) Clearly describe what the figure depicts, its key components, architectural role, and working mechanisms. "
                    f"(d) Break down its working principles clearly and intuitively for the student.\n"
                )
        elif is_global_material:
            curriculum_list_str = ", ".join(context_bundle.curriculum_topics[:8]) if context_bundle.curriculum_topics else "the major curriculum topics across the document"
            if is_questions_only:
                task_instruction = (
                    f"3. PRACTICE QUESTIONS ACROSS ALL TOPICS (WHOLE MATERIAL - QUESTIONS ONLY):\n"
                    f"The student explicitly requested {target_count} questions from the WHOLE study material covering ALL topics (no answers, no solution keys, no hints).\n"
                    f"CRITICAL ANTI-NARROWING RULE: DO NOT restrict the questions to the previous chat topic or a single chapter!\n"
                    f"Distribute the {target_count} questions evenly across the curriculum ({curriculum_list_str}).\n"
                    f"Provide clear, numbered questions with real academic substance. DO NOT include answers, solution keys, or hints.\n"
                )
            else:
                is_important_questions = any(w in query_meta.resolved_query.lower() for w in ["important", "key", "main", "exam"]) or query_meta.visual_diagram_type == "concept_graph"
                graph_hint = ""
                if is_important_questions or query_meta.visual_diagram_type == "concept_graph":
                    graph_hint = (
                        "CONCEPT RELATIONSHIP GRAPH: Before or alongside the questions, generate a comprehensive Mermaid concept relationship graph (```mermaid\nflowchart TD\n...```) mapping how the major curriculum topics and exam areas connect to each other across the entire syllabus! "
                        "Follow with '#### 🔍 Visual Breakdown (How to Read this Diagram)'.\n"
                    )
                ans_str = "For each question, provide a thorough, accurate model answer and pedagogical explanation." if (format_dirs.get("include_answers") or "answer" in query_meta.resolved_query.lower()) else "Provide the questions clearly."
                task_instruction = (
                    f"3. COMPREHENSIVE PRACTICE QUESTIONS (WHOLE MATERIAL - ALL TOPICS):\n"
                    f"The student requested {target_count} questions from the entire study material covering ALL topics.\n"
                    f"CRITICAL ANTI-NARROWING RULE: DO NOT restrict the questions to the previous chat topic (e.g. do NOT focus solely on one model or algorithm discussed earlier)! "
                    f"Evenly distribute the {target_count} questions across distinct chapters and curriculum topics ({curriculum_list_str}).\n"
                    f"Number each question clearly (`### Question 1: [Topic/Chapter Title]`, `### Question 2: [Topic/Chapter Title]`, etc.).\n"
                    f"{ans_str}\n"
                    f"{graph_hint}"
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
                is_important_questions = any(w in query_meta.resolved_query.lower() for w in ["important", "key", "main", "exam"]) or query_meta.visual_diagram_type == "concept_graph"
                graph_hint = ""
                if is_important_questions or query_meta.visual_diagram_type == "concept_graph":
                    graph_hint = (
                        "CONCEPT RELATIONSHIP GRAPH: Before or alongside the questions, generate an insightful Mermaid concept relationship graph (```mermaid\nflowchart TD\n...```) mapping how the core topics, principles, and question themes interconnect so the student can understand the conceptual network before practicing! "
                        "Follow with '#### 🔍 Visual Breakdown (How to Read this Diagram)'.\n"
                    )
                task_instruction = (
                    f"3. PRACTICE QUESTIONS: Generate EXACTLY {target_count} high-yield exam preparation questions on {effective_concept}. "
                    f"Number them cleanly (Question 1, Question 2, ...). "
                    f"{graph_hint}"
                    f"If the student requested explanations or answers, provide clear explanations. DO NOT output an interactive multiple-choice quiz.\n"
                )
        elif is_topics_overview:
            is_seq = any(w in query_meta.resolved_query.lower() for w in ["evolution", "phase", "phases", "step", "steps", "stage", "stages", "pipeline", "history", "timeline"])
            if is_seq or query_meta.visual_diagram_type == "flowchart_lr":
                task_instruction = (
                    "3. CURRICULUM OVERVIEW / PHASES / EVOLUTION: The student is asking for the evolution, phases, or progression of this subject. "
                    "Present a structured, engaging breakdown of the verified phases and key milestones. "
                    "MANDATORY SEQUENTIAL FLOWCHART: You MUST generate a clean horizontal Mermaid flowchart (```mermaid\nflowchart LR\n...```) showing the sequential progression across phases (e.g. Phase 1 --> Phase 2 --> Phase 3 --> Phase 4). "
                    "DO NOT use a radial mindmap for chronological phases! "
                    "Quote all node text containing special characters or parentheses. "
                    "Immediately beneath the flowchart, include '#### 🔍 Visual Breakdown (How to Read this Diagram)', explain the key concepts of each phase, and conclude with the Interactive Checkpoint.\n"
                )
            else:
                task_instruction = (
                    "3. CURRICULUM OVERVIEW / MAIN TOPICS / SYLLABUS PILLARS: The student is asking for the main topics, syllabus pillars, summary, or learning roadmap of this study material. "
                    "Present a structured, engaging breakdown of the verified curriculum and key topics in this document. "
                    "INTERACTIVE OVERVIEW DIAGRAM: Generate a structured Mermaid diagram organizing the core pillars and their subtopics/chapters (use `mindmap` for non-sequential syllabus branches, or `flowchart TD` for hierarchical relationship trees). "
                    "Quote all node text containing parentheses, brackets, colons, or punctuation. "
                    "Immediately beneath the diagram, include '#### 🔍 Visual Breakdown (How to Read this Diagram)' explaining the core pillars and relationships, explain the key concepts of each pillar, and conclude with the Interactive Checkpoint.\n"
                )
        else:
            task_instruction = ""

        target_visual_subject = query_meta.visual_prompt_focus or query_meta.resolved_query
        if is_figure_query and context_bundle.related_figures:
            target_visual_subject = context_bundle.related_figures[0]

        visual_directive = ""
        v_type = getattr(query_meta, "visual_diagram_type", "none")

        if getattr(query_meta, "query_scope", None) == "ambiguous_scope" or is_pasted_mcq or is_batch_questions or query_meta.visual_modality == "none":
            visual_directive = ""
        elif v_type == "flowchart_lr" or (query_meta.visual_modality == "mermaid" and any(w in query_meta.resolved_query.lower() for w in ["evolution", "phase", "phases", "step", "steps", "stage", "stages", "pipeline", "timeline"])):
            visual_directive = (
                f"5. VISUAL GENERATION (HORIZONTAL SEQUENTIAL FLOWCHART): Generate a clean, valid Mermaid horizontal flowchart (```mermaid\nflowchart LR\n...```) representing {target_visual_subject}. "
                "Show the progression cleanly from left to right (e.g. Phase 1 --> Phase 2 --> Phase 3 --> Phase 4). "
                "STRICT RULE: DO NOT use a radial mindmap for chronological or sequential phases! "
                "Quote all node text containing special characters or punctuation. "
                "Immediately beneath the diagram, include '#### 🔍 Visual Breakdown (How to Read this Diagram)' with bullet points explaining each phase and arrow.\n"
            )
        elif v_type == "concept_graph":
            visual_directive = (
                f"5. VISUAL GENERATION (CONCEPT RELATIONSHIP GRAPH): Generate an interconnected Mermaid concept graph (```mermaid\nflowchart TD\n...```) representing {target_visual_subject}. "
                "Map out how the core exam concepts, underlying principles, and question themes relate and connect to each other so the student grasps the conceptual network. "
                "Quote all node text containing special characters or punctuation. "
                "Immediately beneath the diagram, include '#### 🔍 Visual Breakdown (How to Read this Diagram)' explaining the relationships and key exam insights.\n"
            )
        elif v_type == "sequence":
            visual_directive = (
                f"5. VISUAL GENERATION (SEQUENCE DIAGRAM): Generate a clean, valid Mermaid sequence diagram (```mermaid\nsequenceDiagram\n...```) representing the interaction or protocol exchange in {target_visual_subject}. "
                "Immediately beneath the diagram, include '#### 🔍 Visual Breakdown (How to Read this Diagram)' explaining the request-response steps.\n"
            )
        elif v_type == "state_diagram":
            visual_directive = (
                f"5. VISUAL GENERATION (STATE DIAGRAM): Generate a clean Mermaid state diagram (```mermaid\nstateDiagram-v2\n...```) representing the states and transitions of {target_visual_subject}. "
                "Immediately beneath the diagram, include '#### 🔍 Visual Breakdown (How to Read this Diagram)'.\n"
            )
        elif v_type == "svg" or query_meta.visual_modality == "svg":
            is_algo = any(w in query_meta.resolved_query.lower() for w in [
                "algorithm", "binary search", "quicksort", "sort", "merge sort", "dijkstra",
                "bfs", "dfs", "array", "stack", "queue", "tree", "pointer", "graph",
                "dynamic programming", "gradient descent", "backprop", "neural network"
            ])
            if is_algo:
                visual_directive = (
                    f"5. VISUAL GENERATION (ALGORITHM INLINE SVG): Generate a high-clarity, intuitive Inline SVG vector diagram (```svg <svg viewBox=\"0 0 650 320\" xmlns=\"http://www.w3.org/2000/svg\" class=\"w-full\"> ... </svg> ```) illustrating the algorithm {target_visual_subject}. "
                    "Visually depict the data state (e.g. array slots with values and indices), pointers (e.g. low, mid, high or i, j, pivot), comparisons, or node transitions using modern colors (Indigo #6366F1, Emerald #10B981, Amber #F59E0B, Rose #EF4444, Slate #64748B). "
                    "Include legible text labels and arrows. Immediately beneath the SVG, include '#### 🔍 Visual Breakdown (How to Read this Diagram)' explaining each visual element.\n"
                )
            else:
                visual_directive = (
                    f"5. VISUAL GENERATION (INLINE SVG): Generate a beautiful, responsive Inline SVG vector diagram (```svg <svg viewBox=\"0 0 600 350\" xmlns=\"http://www.w3.org/2000/svg\" class=\"w-full\"> ... </svg> ```) illustrating {target_visual_subject}. "
                    "Use modern colors and clear text labels. Immediately beneath the SVG, include '#### 🔍 Visual Breakdown (How to Read this Diagram)' with 3-4 bullet points explaining what each color, shape, line, and boundary represents.\n"
                )
        elif v_type == "mindmap":
            visual_directive = (
                f"5. VISUAL GENERATION (MINDMAP): Generate a structured Mermaid mindmap (```mermaid\nmindmap\n  root((Title))\n    Pillar1\n      [\"Subtopic 1\"]\n...```) representing {target_visual_subject}. "
                "Quote all node text containing special characters or punctuation. Immediately beneath the diagram, include '#### 🔍 Visual Breakdown (How to Read this Diagram)' explaining the core pillars and relationships.\n"
            )
        elif query_meta.visual_modality == "mermaid" or is_topics_overview:
            visual_directive = (
                f"5. VISUAL GENERATION: Generate a clean, valid Mermaid diagram (```mermaid ... ```) representing {target_visual_subject}. "
                "For sequential phases or timelines, use `flowchart LR`. For hierarchies or concept networks, use `flowchart TD`. For non-sequential broad syllabi, use `mindmap`. "
                "Quote all node text containing special characters or punctuation. Immediately beneath the diagram, include '#### 🔍 Visual Breakdown (How to Read this Diagram)' explaining what each part and arrow means.\n"
            )
        elif wants_visual:
            is_algo = any(w in query_meta.resolved_query.lower() for w in [
                "algorithm", "sort", "search", "tree", "array", "pointer", "dijkstra", "stack", "queue", "graph", "neural"
            ])
            if is_algo:
                visual_directive = (
                    "5. VISUAL GENERATION: Generate an Inline SVG vector diagram (```svg <svg viewBox=\"0 0 650 320\" xmlns=\"http://www.w3.org/2000/svg\" class=\"w-full\"> ... </svg> ```) visualizing this algorithm or data structure with colored state boxes, pointers, and step labels. "
                    "Immediately beneath the diagram, include '#### 🔍 Visual Breakdown (How to Read this Diagram)'.\n"
                )
            else:
                visual_directive = (
                    "5. VISUAL GENERATION: A visual aid is beneficial here. Provide the appropriate diagram matching the concept (Inline SVG for algorithms and physical/spatial models, flowchart LR for phases, concept graph/flowchart TD for relationships). "
                    "Immediately beneath the diagram, include a '#### 🔍 Visual Breakdown (How to Read this Diagram)' section.\n"
                )

        if is_global_material:
            subject_focus_display = "Entire Study Material (All Topics / Chapters)"
        else:
            subject_focus_display = context_bundle.topic_title or "Academic Studies"

        user_prompt = (
            f"Subject Focus / Document Title: {subject_focus_display}\n"
            f"Student Question: \"{query_meta.resolved_query}\"\n"
            f"Learning Intent: {query_meta.intent}\n"
            f"{count_str}"
            f"{topic_spec_str}"
            f"Visual aid requested/warranted: {'no' if (is_pasted_mcq or is_batch_questions or getattr(query_meta, 'query_scope', None) == 'ambiguous_scope') else ('yes' if wants_visual or query_meta.visual_modality != 'none' else 'no')}\n"
            f"Visual modality selected: {'none' if (is_pasted_mcq or is_batch_questions or getattr(query_meta, 'query_scope', None) == 'ambiguous_scope') else query_meta.visual_modality}\n"
            f"Visual diagram type: {'none' if (is_pasted_mcq or is_batch_questions or getattr(query_meta, 'query_scope', None) == 'ambiguous_scope') else v_type}\n\n"
            f"{history_str}"
            f"{curriculum_str}"
            f"=== VERIFIED STUDY CONTEXT (from the student's uploaded document) ===\n"
            f"{context_str}\n"
            f"{formulas_str}\n"
            f"{tables_str}\n"
            f"{figures_str}\n"
            f"======================================================================\n\n"
            f"Instructions:\n"
            f"1. Check if the question is within the scope of this study material. If the student asks about any concept or classification covered in the verified excerpts below, or asks about main topics, curriculum, summary, or practice problems, it is 100% IN-SCOPE and must be answered thoroughly.\n"
            f"2. Only decline if the question is completely unrelated to the academic subject (e.g. pop culture, celebrity gossip, stock trading, cooking recipes).\n"
            f"3. Check DIALOGUE HISTORY: If the student asks about ANY of your previous responses or explanations in this session, answer directly and accurately referencing that prior response.\n"
            f"{task_instruction}"
            f"4. Adapt your response format to the query intent (e.g. roadmap for 'main topics', intuitive explanation with analogy for 'explain', table for comparisons, clean LaTeX for math).\n"
            f"{visual_directive}"
            f"6. Do NOT output raw HTML (<br>) or ASCII-art. Use native Markdown only.\n"
            f"7. End with an Interactive Checkpoint active recall question ending in a question mark (?) ONLY for conceptual explanations or lectures. If this response is already a list of practice questions, an exam sheet, or a solved table, do NOT append an Interactive Checkpoint.\n"
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
        # 3. Strip multi-branch navigation menus (skip for pasted MCQs/batch questions to protect options/answers)
        if not (query_meta and (getattr(query_meta, "is_pasted_mcq", False) or getattr(query_meta, "is_batch_questions", False))):
            content = cls._STRIP_MENU_PATTERN.sub("", content)

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

        # If this is practice questions, student requested only questions, table solving, pasted MCQ/batch solving, or answer_only depth, do not append artificial checkpoint
        is_exempt = query_meta and (
            query_meta.intent == "PRACTICE_QUESTIONS"
            or (query_meta.format_directives and query_meta.format_directives.get("questions_only"))
            or (query_meta.format_directives and query_meta.format_directives.get("solve_table"))
            or query_meta.referenced_table is not None
            or getattr(query_meta, "is_pasted_mcq", False)
            or getattr(query_meta, "is_batch_questions", False)
            or (query_meta.pre_gen_plan and (query_meta.pre_gen_plan.skip_followup_question or query_meta.pre_gen_plan.depth == "answer_only"))
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

            if context_bundle.related_figures:
                sections.append("### 🖼️ Document Figures on Referenced Page")
                for fig in context_bundle.related_figures:
                    sections.append(f"- **{fig}**")
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
                if (
                    llm_content
                    and len(llm_content.strip()) > _MIN_LIVE_RESPONSE_CHARS
                    and "reconnecting to the AI language model service" not in llm_content
                ):
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
                    "LLM returned empty/short or fallback response; falling back to context-grounded excerpt."
                )
            except Exception as e:
                logger.error(
                    f"Live LLM generation failed: {e}. "
                    "Falling back to context-grounded excerpt."
                )

        # Fallback: format retrieved chunks directly (clean LaTeX, no hardcoded text)
        content = cls._context_grounded_fallback(query, topic_title, context_bundle)
        content = cls._enforce_response_contract(content, topic_title, query_meta)
        return TeachingResponse(
            content=content,
            intent=query_meta.intent,
            citations=context_bundle.citations,
            grounding_score=0.85,
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
                tokens_accum = []
                for token in default_llm_service.stream_generate(
                    prompt=user_prompt, system_prompt=system_prompt
                ):
                    tokens_accum.append(token)
                
                full_streamed = "".join(tokens_accum)
                if (
                    full_streamed
                    and "reconnecting to the AI language model service" not in full_streamed
                    and len(full_streamed.strip()) > _MIN_LIVE_RESPONSE_CHARS
                ):
                    for tok in tokens_accum:
                        yield tok
                    return
                logger.warning("LLM stream yielded reconnecting message or empty; falling back to context excerpts.")
            except Exception as e:
                logger.error(f"Live LLM token streaming failed: {e}. Falling back to excerpts.")

        # Fallback: stream the context-grounded excerpt word by word
        response_text = cls._context_grounded_fallback(query, topic_title, context_bundle)
        response_text = cls._enforce_response_contract(response_text, topic_title, query_meta)
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
