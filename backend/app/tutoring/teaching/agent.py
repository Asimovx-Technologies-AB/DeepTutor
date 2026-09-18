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

1. DEFINITION & TOPIC EXPLANATION (e.g. "what is X", "define X", "explain X", "explain [topic]"):
   - PHILOSOPHY: Keep it SHORT, SIMPLE, and EASY TO UNDERSTAND. A student should grasp the concept in one quick read. No walls of text!
   - STRICT RESPONSE FORMAT:
     * ONE Short Paragraph: Explain the entire concept in a SINGLE short paragraph (3-5 sentences max) using simple everyday language. Cover what it is, what it does, and why it matters — all in one compact paragraph.
     * Key Points (bullet list): List the important subtopics, features, or components as clean bullet points:
       - **[Key Point Name]**: One simple sentence explaining it.
       - **[Key Point Name]**: One simple sentence explaining it.
       - (3-5 bullet points max — cover only the important ones)
     * THAT'S IT. Do NOT add extra paragraphs, trailing summaries, "the analysis process...", or any other filler text after the bullet points.
     * NO UNREQUESTED FLUFF: No multiple paragraphs, no verbose repetitions, no trailing explanations after the bullets. Keep the total response SHORT and scannable.
     * Visual Diagram (ONLY if explicitly requested by the student):
       - A clean Mermaid flowchart or SVG diagram.
       - Followed by `#### 🔍 Visual Breakdown (How to Read this Diagram)` with 3-4 bullet points.
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
   - MANDATORY SET HEADING & CONCEPT TAGGING:
     * MUST always start with a prominent Markdown heading indicating the topic/chapter:
       `### 📝 Practice Questions: [Topic/Concept Name]`
     * Number each question cleanly with a bold subtopic or concept tag:
       `1. **[Core Subtopic/Concept]**: [Clear, rigorous question prompt]`
       `2. **[Core Subtopic/Concept]**: [Clear, rigorous question prompt]`
       This ensures students can reference questions by number or concept tag at any point in the conversation.
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

9. CURRICULUM OVERVIEW & IMPORTANT TOPICS (e.g. "what are the main topics", "what are the important topics", "curriculum", "syllabus", "topics in this document"):
   - Structure:
     * Brief Context Header: 1 concise introductory sentence acknowledging the document subject and scope.
     * Structured Topic Breakdown (MANDATORY PROPER FORMAT):
       🚫 You MUST NEVER output all topics in a single run-on sentence or comma-separated paragraph!
       Format each topic clearly with Markdown structure:
       ### 📚 Key Topics in this Material
       1. **[Topic Name]**
          - **What it covers**: 1-2 concise sentences summarizing the core principles and scope of this topic.
          - **Exam Focus / Key Highlights**: Key mechanisms, fundamental formulas, or high-yield exam takeaways.
     * Suggested Next Step:
       Conclude warmly with a question inviting the student to choose which topic to explore first:
       "Which of these topics would you like to explore or practice first?"

=== MULTI-TURN CONVERSATION MEMORY ===
- You have full access to the previous conversation history in this study session.
- If the student asks about something you explained earlier, or asks a follow-up referencing ANY prior response, answer, or question, refer accurately and coherently to what you previously taught or answered in this session.

=== STRICT QUERY-SPECIFIC FOCUS ===
- When the student asks specifically about a particular topic, subtopic, detail, question, calculation, or concept:
  * Answer ONLY and directly based on what the student specifically asked.
  * Do NOT expand into unrequested broader lectures, unasked-for topics, or extraneous boilerplate.
  * Keep the explanation easy to understand for the student, using clear simple language and concise bullet points for any key components.

=== CRITICAL MARKDOWN & TYPOGRAPHY CONSTRAINTS ===
- LANGUAGE SIMPLICITY: Write in a clear, friendly, conversational teaching voice. Do NOT use overly dense corporate or academic jargon (e.g., avoid "installing sophisticated architectural partitions", "abstracts CPU/memory resources", or "encapsulation as a file bundle" when you can say "divides one computer into separate private rooms" or "saves each virtual machine like a normal document").
- BREVITY IS KEY: Keep responses SHORT. One paragraph for the explanation + bullet points for key features = done. Do NOT write multiple long paragraphs or add trailing summaries after the bullet points. Students want quick, clear answers — not essays.
- NO MONOLITHIC WALLS OF TEXT: Keep paragraphs short (maximum 3-5 sentences per paragraph).
- ALWAYS leave an empty line (double newline) before and after headers (`###`), horizontal dividers (`---`), and bullet lists (`*`).
- Bold key terms to make the explanation immediately scannable.
- Do NOT output any raw HTML tags (never use `<br>`, `<p>`, or `<div>`). Use native Markdown newlines and formatting only.
- Do NOT output ASCII-art diagrams or pseudo-code text boxes.
- Standard LaTeX syntax:
  - Inline math: `$variable$` or `$x + y$` for single variables, symbols, and inline formulas (e.g., `$Q$`, `$K$`, `$V$`, `$d_k$`).
  - Display block math: `$$ formula $$` on standalone lines for display equations.
  - CRITICAL: NEVER put plain English sentences or labels inside `$ ... $` or `$$ ... $$` unless enclosed in `\\text{...}`.

=== MATERIAL-GROUNDED & GENERAL ACADEMIC KNOWLEDGE ===
- Prioritize the verified context excerpts, figures, and tables provided below.
- If the student specifically asks about what is contained in the uploaded document/notes and it is not found, state that the material does not cover it.
- If the student asks a general academic, factual, scientific, or mathematical question (e.g. general periodic table questions, math calculations), answer it accurately and directly from academic knowledge without refusing.
- NEVER produce robotic refusal boilerplate such as "I am your dedicated tutor for this study material...". Keep responses natural and helpful.
- MANDATORY IN-SCOPE EXCEPTIONS (NEVER REFUSE):
  1. Main Topics & Curriculum Overview: Questions asking "what are the main topics", "what does this document cover", "give me a summary", or "syllabus" are ALWAYS IN-SCOPE.
  2. Pedagogical & Dialogue Requests: Requests for practice questions, quizzes, problem solving, explaining simpler, or asking about earlier conversation turns in this session are ALWAYS IN-SCOPE.

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
   - When a diagram/image is generated, structure the response cleanly:
     1. The visual diagram block (```svg ... ``` or ```mermaid ... ```).
     2. Exactly ONE simple, intuitive explanation in a single concise paragraph explaining the core concept in plain English.
     3. Followed by the visual breakdown:
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

_MIN_LIVE_RESPONSE_CHARS = 1


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
        cls, query_meta: QueryMetadata, context_bundle: ContextBundle, is_teacher_mode: bool = False
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
            if not is_teacher_mode or plan.skip_followup_question or plan.depth == "answer_only":
                followup_constraint_str = "INTERACTIVE CHECKPOINT CONSTRAINT: DO NOT include any `### 💡 Interactive Checkpoint` or follow-up question. End the response cleanly after the answer."
            else:
                followup_constraint_str = "INTERACTIVE CHECKPOINT CONSTRAINT: Conclude with the `### 💡 Interactive Checkpoint` active recall question."

            hard_constraints_block = (
                "=== PRE-GENERATION HARD CONSTRAINTS (MANDATORY TO OBEY) ===\n"
                f"- {depth_instruction}\n"
                f"- {format_instruction}\n"
                f"- {visual_constraint_str}\n"
                f"- {followup_constraint_str}\n"
                f"- Strategy Reasoning: {plan.reasoning}\n"
            )
            
            # Enforce output requirements if they exist
            out_reqs = getattr(query_meta, "output_requirements", None)
            if out_reqs:
                if out_reqs.format == "ANSWER_ONLY":
                    hard_constraints_block += "- OUTPUT CONSTRAINT: Provide ONLY the direct answer. DO NOT include any explanatory text, greetings, bullet points, or concluding checkpoints. Output exactly what is requested and nothing more.\n"
                elif out_reqs.format == "BULLETS_ONLY":
                    hard_constraints_block += "- OUTPUT CONSTRAINT: Provide the answer strictly in bullet points. DO NOT include introductory or concluding paragraphs.\n"
                    
                if out_reqs.length == "SHORT":
                    hard_constraints_block += "- LENGTH CONSTRAINT: Keep the response extremely brief, no more than 2-3 sentences.\n"
                elif out_reqs.length == "LONG":
                    hard_constraints_block += "- LENGTH CONSTRAINT: Provide a comprehensive and detailed response, breaking down all nuances.\n"
                    
                if not out_reqs.include_explanation:
                    hard_constraints_block += "- EXPLANATION CONSTRAINT: DO NOT explain your reasoning. Provide only the final result or direct answer.\n"
                if not out_reqs.include_examples:
                    hard_constraints_block += "- EXAMPLES CONSTRAINT: DO NOT include any examples or analogies.\n"
                if not out_reqs.include_steps:
                    hard_constraints_block += "- STEPS CONSTRAINT: DO NOT show step-by-step working, provide only the final answer.\n"

            hard_constraints_block += "===========================================================\n\n"
        elif not is_teacher_mode:
            hard_constraints_block = (
                "=== PRE-GENERATION HARD CONSTRAINTS (MANDATORY TO OBEY) ===\n"
                "- INTERACTIVE CHECKPOINT CONSTRAINT: DO NOT include any `### 💡 Interactive Checkpoint` or active recall questions. Keep response clean and focused.\n"
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
                    f"3. PRACTICE QUESTIONS (MANDATORY SET HEADING & CONCEPT ANCHORS):\n"
                    f"Generate EXACTLY {target_count} high-yield exam preparation questions on {effective_concept}.\n"
                    f"- MANDATORY SET HEADING: You MUST start your response with: '### 📝 Practice Questions: {effective_concept}'\n"
                    f"- NUMBERED QUESTIONS WITH CONCEPT ANCHORS:\n"
                    f"  1. **[Specific Subtopic/Concept]**: [Clear, rigorous question statement]\n"
                    f"  2. **[Specific Subtopic/Concept]**: [Clear, rigorous question statement]\n"
                    f"{graph_hint}"
                    f"If the student requested explanations or answers, provide clear explanations. DO NOT output an interactive multiple-choice quiz.\n"
                )
        elif is_topics_overview:
            is_seq = any(w in query_meta.resolved_query.lower() for w in ["evolution", "phase", "phases", "step", "steps", "stage", "stages", "pipeline", "history", "timeline"])
            if is_seq or query_meta.visual_diagram_type == "flowchart_lr":
                task_instruction = (
                    "3. CURRICULUM OVERVIEW / PHASES / EVOLUTION: The student is asking for the evolution, phases, or progression of this subject. "
                    "Present a structured, engaging breakdown of the verified phases and key milestones. "
                    "MANDATORY SEQUENTIAL DIAGRAM: You MUST generate a clean, responsive Inline SVG vector diagram (```svg <svg viewBox=\"0 0 650 320\" ...> ... </svg> ```) showing the sequential progression across phases (e.g. Phase 1 --> Phase 2 --> Phase 3 --> Phase 4). "
                    "Include legible text labels and arrows. "
                    "Immediately beneath the flowchart, include '#### 🔍 Visual Breakdown (How to Read this Diagram)', explain the key concepts of each phase, and conclude with the Interactive Checkpoint.\n"
                )
            else:
                task_instruction = (
                    "3. CURRICULUM OVERVIEW & IMPORTANT TOPICS (STRICT PROPER FORMATTING REQUIRED):\n"
                    "The student is asking for the important topics, curriculum overview, or syllabus pillars of this study material.\n"
                    "MANDATORY FORMATTING INSTRUCTIONS:\n"
                    "- 🚫 NEVER collapse or dump all topics together into a single run-on sentence paragraph separated by commas!\n"
                    "- Format the response cleanly using structured Markdown:\n"
                    "  Start with a brief, encouraging introduction (e.g., 'Here are the key topics covered in your study material:').\n"
                    "  Then present each verified topic as a clean numbered section or bulleted item:\n"
                    "  1. **[Topic Title]**\n"
                    "     - **What it covers:** 1-2 concise sentences summarizing the core concepts from the verified text.\n"
                    "     - **Exam Focus:** Key formulas, mechanisms, or high-yield problem types.\n"
                    "  Repeat this clean structure for each topic from the verified curriculum.\n"
                    "- Conclude warmly by asking: 'Which of these topics would you like to explore first?'\n"
                )
        else:
            task_instruction = ""

        target_visual_subject = query_meta.visual_prompt_focus or query_meta.resolved_query
        if is_figure_query and context_bundle.related_figures:
            target_visual_subject = context_bundle.related_figures[0]

        visual_directive = ""
        v_type = getattr(query_meta, "visual_diagram_type", "none")

        is_image_only_intent = False
        if query_meta.visual_modality == "svg" and any(w in query_meta.resolved_query.lower() for w in ["draw", "image", "picture", "figure", "illustration", "visualize", "diagram", "svg"]):
            is_image_only_intent = True

        if is_image_only_intent:
            visual_directive = (
                f"5. VISUAL GENERATION & EXPLANATION: The student requested an image or diagram of {target_visual_subject}. "
                "Structure your response strictly in the following order:\n"
                "1. Generate a high-clarity, beautiful Inline SVG vector diagram (```svg <svg viewBox=\"0 0 650 350\" xmlns=\"http://www.w3.org/2000/svg\" class=\"w-full\"> ... </svg> ```).\n"
                "2. Immediately beneath the diagram, provide exactly ONE simple, intuitive explanation in a single concise paragraph explaining the concept in clear, plain language.\n"
                "3. Follow with '#### 🔍 Visual Breakdown (How to Read this Diagram)' with a concise bulleted explanation of what each shape, color, line/arrow represents, concluding with the Key Insight.\n"
                "4. Conclude with the '### 💡 Interactive Checkpoint' active recall question.\n"
            )
        elif getattr(query_meta, "query_scope", None) == "ambiguous_scope" or is_pasted_mcq or is_batch_questions or query_meta.visual_modality == "none":
            visual_directive = ""
        elif query_meta.visual_modality == "mermaid" or v_type in ("flowchart_td", "mermaid"):
            visual_directive = (
                f"5. VISUAL GENERATION (MERMAID FLOWCHART): Generate a clean Mermaid flowchart (```mermaid ... ```) representing {target_visual_subject}. "
                "Use flowchart TD or flowchart LR as appropriate with clear labels. "
                "Immediately beneath the diagram, include '#### 🔍 Visual Breakdown (How to Read this Diagram)' explaining the flow.\n"
            )
        elif v_type == "flowchart_lr" or (query_meta.visual_modality == "svg" and any(w in query_meta.resolved_query.lower() for w in ["evolution", "phase", "phases", "step", "steps", "stage", "stages", "pipeline", "timeline"])):
            visual_directive = (
                f"5. VISUAL GENERATION (HORIZONTAL SEQUENTIAL FLOW): Generate a clean, valid Inline SVG diagram (```svg <svg viewBox=\"0 0 700 250\" xmlns=\"http://www.w3.org/2000/svg\" class=\"w-full\"> ... </svg> ```) representing {target_visual_subject}. "
                "Show the progression cleanly from left to right (e.g. Phase 1 --> Phase 2 --> Phase 3 --> Phase 4) using modern colors and clear text labels. "
                "Immediately beneath the diagram, include '#### 🔍 Visual Breakdown (How to Read this Diagram)' with bullet points explaining each phase and arrow.\n"
            )
        elif v_type == "concept_graph":
            visual_directive = (
                f"5. VISUAL GENERATION (CONCEPT RELATIONSHIP GRAPH): Generate an interconnected Inline SVG concept graph (```svg <svg viewBox=\"0 0 650 450\" xmlns=\"http://www.w3.org/2000/svg\" class=\"w-full\"> ... </svg> ```) representing {target_visual_subject}. "
                "Map out how the core exam concepts, underlying principles, and question themes relate and connect to each other so the student grasps the conceptual network. "
                "Immediately beneath the diagram, include '#### 🔍 Visual Breakdown (How to Read this Diagram)' explaining the relationships and key exam insights.\n"
            )
        elif v_type == "sequence":
            visual_directive = (
                f"5. VISUAL GENERATION (SEQUENCE DIAGRAM): Generate a clean, valid Inline SVG sequence diagram (```svg <svg viewBox=\"0 0 600 400\" xmlns=\"http://www.w3.org/2000/svg\" class=\"w-full\"> ... </svg> ```) representing the interaction or protocol exchange in {target_visual_subject}. "
                "Use vertical swimlanes/lifelines and horizontal message arrows. Immediately beneath the diagram, include '#### 🔍 Visual Breakdown (How to Read this Diagram)' explaining the request-response steps.\n"
            )
        elif v_type == "state_diagram":
            visual_directive = (
                f"5. VISUAL GENERATION (STATE DIAGRAM): Generate a clean Inline SVG state diagram (```svg <svg viewBox=\"0 0 650 350\" xmlns=\"http://www.w3.org/2000/svg\" class=\"w-full\"> ... </svg> ```) representing the states and transitions of {target_visual_subject}. "
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
                f"5. VISUAL GENERATION (MINDMAP): Generate a structured Inline SVG radial mindmap (```svg <svg viewBox=\"0 0 700 450\" xmlns=\"http://www.w3.org/2000/svg\" class=\"w-full\"> ... </svg> ```) representing {target_visual_subject}. "
                "Immediately beneath the diagram, include '#### 🔍 Visual Breakdown (How to Read this Diagram)' explaining the core pillars and relationships.\n"
            )
        elif query_meta.visual_modality == "svg" or is_topics_overview:
            visual_directive = (
                f"5. VISUAL GENERATION: Generate a clean, valid Inline SVG diagram (```svg <svg viewBox=\"0 0 650 350\" xmlns=\"http://www.w3.org/2000/svg\" class=\"w-full\"> ... </svg> ```) representing {target_visual_subject}. "
                "Immediately beneath the diagram, include '#### 🔍 Visual Breakdown (How to Read this Diagram)' explaining what each part and arrow means.\n"
            )
        elif wants_visual:
            visual_directive = (
                "5. VISUAL GENERATION: Generate an Inline SVG vector diagram (```svg <svg viewBox=\"0 0 650 320\" xmlns=\"http://www.w3.org/2000/svg\" class=\"w-full\"> ... </svg> ```) visualizing this concept or data structure with colored state boxes, pointers, and step labels. "
                "Immediately beneath the diagram, include '#### 🔍 Visual Breakdown (How to Read this Diagram)'.\n"
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
        cls,
        content: str,
        topic_title: str,
        query_meta: Optional[QueryMetadata] = None,
        is_teacher_mode: bool = False,
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

        # Format Curriculum / Topics Overview if collapsed into a single run-on sentence
        is_topics_overview = query_meta and (
            query_meta.intent == "SUMMARY"
            or any(w in query_meta.resolved_query.lower() for w in ["main topic", "topics", "summary", "overview", "syllabus", "roadmap", "chapters", "curriculum"])
        )
        if is_topics_overview:
            single_para = len([p for p in content.split("\n\n") if p.strip()]) <= 2
            has_no_list = not any(line.strip().startswith(("-", "*", "1.", "2.")) for line in content.split("\n"))
            if single_para and has_no_list:
                inc_match = re.search(r"^(.*?include(?:s|d)?\s+)(.+?)[\.\?!]?$", content, re.IGNORECASE | re.DOTALL)
                if inc_match:
                    intro = inc_match.group(1).strip().rstrip(":")
                    raw_topics = inc_match.group(2).strip()
                    topics = re.split(r',\s*(?:and\s+)?', raw_topics)
                    topics = [t.strip().rstrip('.') for t in topics if t.strip()]
                    if len(topics) >= 2:
                        formatted = f"{intro}:\n\n"
                        for idx, top in enumerate(topics, 1):
                            formatted += f"{idx}. **{top}**\n"
                        formatted += "\nWhich of these topics would you like to explore first?"
                        content = formatted

        # If this is practice questions, student requested only questions, table solving, pasted MCQ/batch solving, or answer_only depth, do not append artificial checkpoint
        is_exempt = not is_teacher_mode or (query_meta and (
            query_meta.intent == "PRACTICE_QUESTIONS"
            or (query_meta.format_directives and query_meta.format_directives.get("questions_only"))
            or (query_meta.format_directives and query_meta.format_directives.get("solve_table"))
            or query_meta.referenced_table is not None
            or getattr(query_meta, "is_pasted_mcq", False)
            or getattr(query_meta, "is_batch_questions", False)
            or (query_meta.pre_gen_plan and (query_meta.pre_gen_plan.skip_followup_question or query_meta.pre_gen_plan.depth == "answer_only"))
        ))
        if is_exempt:
            content = re.sub(r"###\s*💡\s*Interactive Checkpoint.*", "", content, flags=re.DOTALL).strip()
            content = re.sub(r"\*\*Would you like me to continue to the next subtopic\?\*\*", "", content, flags=re.IGNORECASE).strip()
            if query_meta and (query_meta.intent == "PRACTICE_QUESTIONS" or (query_meta.format_directives and query_meta.format_directives.get("questions_only"))):
                if not re.search(r"^###?\s*.*(?:questions|practice)", content, re.IGNORECASE | re.MULTILINE):
                    clean_topic = topic_title or "Practice Questions"
                    content = f"### 📝 Practice Questions: {clean_topic}\n\n{content}"
            return content

        # 5. Ensure Interactive Checkpoint exists for teaching explanations when in teaching mode
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
        cls, query_meta: QueryMetadata, context_bundle: ContextBundle, is_teacher_mode: bool = False
    ) -> TeachingResponse:
        """
        Every query is processed by the configured live LLM using the retrieved
        ContextBundle. Adapts dynamically to query intent and enforces out-of-scope guardrail.
        """
        query = query_meta.resolved_query
        topic_title = cls._clean_topic_title(context_bundle.topic_title)
        question_subject = topic_title if topic_title != "this concept" else "this concept"

        system_prompt, user_prompt = cls._build_prompts(query_meta, context_bundle, is_teacher_mode=is_teacher_mode)

        if default_llm_service.is_live_model_configured():
            try:
                llm_content = default_llm_service.generate(
                    prompt=user_prompt, system_prompt=system_prompt
                )
                if (
                    llm_content
                    and len(llm_content.strip()) >= _MIN_LIVE_RESPONSE_CHARS
                    and "reconnecting to the AI language model service" not in llm_content
                ):
                    content = cls._enforce_response_contract(llm_content.strip(), topic_title, query_meta, is_teacher_mode=is_teacher_mode)
                    is_refusal = "outside the scope of your uploaded" in content.lower()
                    return TeachingResponse(
                        content=content,
                        intent=query_meta.intent,
                        citations=[] if is_refusal else context_bundle.citations,
                        grounding_score=0.3 if is_refusal else 0.98,
                        socratic_follow_up="" if (not is_teacher_mode or is_refusal) else cls._default_follow_up(topic_title),
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
        content = cls._enforce_response_contract(content, topic_title, query_meta, is_teacher_mode=is_teacher_mode)
        return TeachingResponse(
            content=content,
            intent=query_meta.intent,
            citations=context_bundle.citations,
            grounding_score=0.85,
            socratic_follow_up=cls._default_follow_up(topic_title) if is_teacher_mode else "",
            suggested_questions=[
                "Can you explain this concept in a different way?",
                "What are the main differences vs. alternative approaches?",
                "How does this connect to other topics in the document?",
            ],
        )

    @classmethod
    def stream_teaching_tokens(
        cls, query_meta: QueryMetadata, context_bundle: ContextBundle, is_teacher_mode: bool = False
    ) -> Generator[str, None, None]:
        """
        Streams response tokens via SSE.
        Uses live-model token stream when configured; falls back to
        context-grounded excerpt stream.
        """
        query = query_meta.resolved_query
        topic_title = cls._clean_topic_title(context_bundle.topic_title)
        system_prompt, user_prompt = cls._build_prompts(query_meta, context_bundle, is_teacher_mode=is_teacher_mode)

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
                    and len(full_streamed.strip()) >= _MIN_LIVE_RESPONSE_CHARS
                ):
                    for tok in tokens_accum:
                        yield tok
                    return
                logger.warning("LLM stream yielded reconnecting message or empty; falling back to context excerpts.")
            except Exception as e:
                logger.error(f"Live LLM token streaming failed: {e}. Falling back to excerpts.")

        # Fallback: stream the context-grounded excerpt word by word
        response_text = cls._context_grounded_fallback(query, topic_title, context_bundle)
        response_text = cls._enforce_response_contract(response_text, topic_title, query_meta, is_teacher_mode=is_teacher_mode)
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
