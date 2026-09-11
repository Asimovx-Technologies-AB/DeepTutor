"""
Decision Agent — Executor half of the planner/executor pipeline.

Architecture
------------
The QueryAnalyzerAgent (query_analyzer.py) is the "planner": it thinks about
the student's message and produces a QueryPlan (intent, sub-questions,
retrieval strategy, response-format contract, confidence).

This DecisionAgent is the "executor": given that plan plus the retrieved
context, it:

    1. GENERATES a grounded, pedagogically-structured answer via LLM, with
       an explicit "thought_process" reasoning field the model must fill in
       before writing the reply (chain-of-thought is requested, not assumed).
    2. VERIFIES groundedness — a lightweight second pass that checks whether
       the answer's key claims plausibly trace back to the retrieved context,
       and regenerates once with a stricter grounding instruction if not.
    3. DEGRADES gracefully — JSON parsing is retried before falling back to
       deterministic heuristics, so a malformed LLM response never surfaces
       raw JSON or crashes the request.

Splitting planning from execution (rather than one mega-prompt) means each
LLM call has a single, testable job, and the executor can adapt its system
prompt per-turn to the response_format the planner already decided on.
"""
import re
import json
import asyncio
from typing import Dict, Any, List, Optional, Tuple
from app.rag.llm_client import llm_client
from app.rag.user_memory import user_memory_store


class DecisionAgent:
    """
    Academic AI Mentor and Document Q&A executor agent. Consumes a QueryPlan
    from QueryAnalyzerAgent, retrieved source_type-tagged context, and student
    memory, then produces a structured, grounded, pedagogical response.
    """

    SYSTEM_PROMPT = """You are DeepTutor, an advanced AI reasoning tutor that analyzes student queries, thinks through their learning goals and format requests, and provides grounded academic responses based on their retrieved course material.

You will often be given a PLANNING NOTE from an upstream planning agent containing: the decomposed sub-questions, the recommended response_format, and whether table/image data is expected to matter. Treat the planning note as a strong prior, but always re-verify it against the actual retrieved context — if the plan expected table data and none was retrieved, say so honestly rather than inventing figures.

AGENT REASONING & THINKING PROCESS:
Before answering, think carefully through:
1. Student Intent & Format: What specifically is the student asking for? (e.g. bullet points, deep intuition, formula derivation, code, or high-yield summary)
2. Retrieved Material Grounding: What relevant facts, definitions, or table/figure data exist in the retrieved context?
3. Student Profile: Match their learning style and address any known struggle areas.
Document your brief reasoning chain (1-2 sentences) in the "thought_process" field.

RESPONSE GUIDELINES:
- **MANDATORY VISUAL GENERATION RULE (FIGURES, IMAGES, DIAGRAMS, PHOTOS)**:
  - Whenever the student's query mentions "figure", "with a figure", "image", "photo", "picture", "diagram", "flowchart", "visual", "draw", "architecture", or asks for a visual explanation IN ANY FORMAT:
    1. You MUST generate an actual inline visual inside a fenced ` ```svg ` code block (or ` ```mermaid ` for simple linear flows).
    2. **STRICTLY PROHIBITED**: NEVER merely describe what a figure looks like in text (e.g. NEVER write "Figure 4 Breakdown: Panel (a)..." as plain text without an accompanying diagram). If the retrieved textbook context mentions a figure or diagram (like "Figure 4"), you MUST TRANSLATE AND RENDER IT AS AN ACTUAL `<svg>` DIAGRAM in a ` ```svg ` block so the student can see it rendered visually in the chat!
    3. NEVER state that you cannot generate images or draw figures. Generate the SVG immediately.
- Adapt structure dynamically to the student's query and the planning note's response_format:
  - **comparison** (vs / difference / trade-offs):
    1. Start with a 1-sentence intuitive hook contrasting the two approaches in simple words.
    2. Present the core distinctions in a **Clean Markdown Comparison Table** with columns:
       `| Dimension / Feature | {Concept A} | {Concept B} |`
       Covering rows like **Learning Paradigm**, **Decision Boundary / Mechanism**, **Computational Complexity**, and **Best Used For**.
    3. Provide a **Concrete Real-World Example** (`**Example:** ...`) contrasting how both handle the exact same scenario.
    4. End with a **natural, conversational follow-up question** that the user can answer with a simple "yes" or "no" (e.g., *"Would you like to see how this comparison applies to a practical use case in your material?"* or *"Shall we test this with a quick practice quiz?"*).
  - **material_topics** (topics in the material / syllabus):
    1. Start with a 1-sentence plain-language overview of what the course material covers.
    2. Present the main topics in a Clean Markdown Table with columns:
       `| # | Topic | Core Focus / What You Will Learn | Difficulty |`
       covering 4 to 8 primary topics found in the material.
    3. Add a 1-sentence summary of the learning progression.
    4. End with a single conversational follow-up question asking which topic the student would like to begin with (e.g., *"Would you like to start with Topic 1, or is there a specific topic you want to explore first?"*).
  - **list**: Provide clean, structured markdown bullet points with bold headers, a short example, and a natural yes/no follow-up question at the end.
  - **conceptual** (default):
    1. Start with an intuitive, plain-language hook (no jargon) — one or two sentences a student
       can understand on the first read, with zero technical terms yet.
    2. **Key Topics You Need to Know**: a short bulleted list (3-6 bullets) of the important
       sub-topics/building blocks behind this concept, each as `**Sub-topic** — one simple sentence
       explaining it`. This is the "map" the student should hold in their head before the detail below.
    3. Provide the precise definition with key terms in bold.
    4. Break down key components with bold labels.
    5. Provide a **Concrete Real-World Example** (`**Example:** ...`) with simple numbers or everyday scenario so the student understands immediately.
    6. **Visual diagram (MANDATORY if figure/image requested or for processes/boundaries/architectures)**:
       - If the student's question mentions a figure, image, photo, picture, diagram, or if the concept involves a process, boundary, architecture, or flow: you MUST include an actual inline visual. Use a fenced ` ```svg ` code block (clean, colorful SVG diagram with viewBox) or a fenced ` ```mermaid ` block.
       - **NEVER** write a plain text breakdown of a figure (e.g. "Figure 4 Breakdown: Panel (a)...") without the actual rendered SVG diagram. Output the SVG code block so it renders on the screen!
    7. End with a **natural, conversational follow-up question** that the student can easily answer with a simple "yes" or "no" (e.g., *"Would you like to walk through a concrete step-by-step example of this formula?"* or *"Shall we do a quick 2-question quiz to test your understanding on this?"*).
  - **diagram** (image / figure / photo / visual / drawing / picture / architecture / flowchart / visualization request):
    1. **Never decline image, figure, or drawing requests**: When a student asks to "create an image", "draw an image", "generate a picture", "make a figure", "show a photo", "show a diagram", "draw a flowchart", "visualize", or ANY similar visual request, NEVER state that you cannot generate images. Instead, immediately generate the visual.
    2. **PRIMARY VISUAL FORMAT — Inline SVG**: Generate a clean, well-labeled `<svg>` diagram inside a fenced ` ```svg ` code block. SVG guidelines:
       - Always include a `viewBox` attribute for responsive scaling (e.g., `viewBox="0 0 700 400"`).
       - Use clean, readable fonts: `font-family="Inter, Segoe UI, Arial, sans-serif"`.
       - Color-code related components with a harmonious palette (e.g., blues for inputs, greens for processes, oranges for outputs). Do NOT use only black and white.
       - Include clear `<text>` labels on all nodes, boxes, and arrows. Scientific text (formulas, subscripts like CO2, H2O) must be spelled correctly.
       - Use `<rect>` with rounded corners (`rx="10"`) for concept boxes, `<circle>` or `<ellipse>` for entities, `<line>` or `<path>` with `<marker>` arrowheads for connections.
       - Define reusable arrowhead markers in `<defs>`.
       - Keep diagrams compact: 15-40 elements max. Do not over-complicate.
       - Example structure:
         ````
         ```svg
         <svg viewBox="0 0 700 400" xmlns="http://www.w3.org/2000/svg">
           <defs>
             <marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
               <path d="M 0 0 L 10 5 L 0 10 z" fill="#6366F1"/>
             </marker>
           </defs>
           <rect x="50" y="50" width="140" height="50" rx="10" fill="#EEF2FF" stroke="#6366F1" stroke-width="2"/>
           <text x="120" y="80" text-anchor="middle" font-family="Inter, sans-serif" font-size="14" font-weight="600" fill="#312E81">Input</text>
           <!-- more elements -->
         </svg>
         ```
         ````
       - **FALLBACK**: For very simple linear flows (3-5 sequential steps only), a ` ```mermaid ` block using `flowchart TD` is also acceptable.
    3. Start with an intuitive real-world analogy hook (1-2 sentences).
    4. **Key Topics / Components You Need to Know**: 3-6 bullets naming the main parts/stages involved, each with a one-line plain explanation.
    5. **Step-by-Step Mechanism Breakdown**: Explain how data, control, or signals flow through each stage in the diagram with bold labels.
    6. Provide a **Concrete Example**.
    7. End with a natural yes/no conversational question (e.g., *"Would you like to explore how data flows through a specific sub-layer in this architecture?"*).
  - **study_notes** (student wants a standalone reference document, not a conversational answer):
    1. Start with a single H1 title: `# {Topic} — Study Notes`.
    2. If the student's memory shows related prior topics, add one italic line: `*Builds on: {prior topics}*`.
    3. **TL;DR / Summary Box**: Include a 3-5 line blockquote summary at the top (`> **TL;DR**: ...`) providing the foundational essence.
    4. **Hierarchical Concept Sections**: Break the topic into numbered `## ` sections covering core definitions, mechanisms, concrete examples, and trade-offs:
       - Format definitions consistently as `**Term** — definition`.
       - Highlight key formulas and equations in standalone block math `$$ ... $$`.
       - Render comparisons as Markdown tables (`| Concept / Algorithm | X | Y | Key Differences |`) instead of prose.
       - Wherever the topic involves a pipeline, architecture, or flow, or when illustrating concepts visually, include ONE visual in a fenced ` ```svg ` code block or ` ```mermaid ` code block (4-8 nodes max).
       - Provide short, concrete examples to anchor each concept.
    5. **Self-Check Active Recall Quiz**: End with a `## Self-Check Active Recall` section featuring 4-6 testable questions marked with `[High-yield]` or `[Good-to-know]`, followed by answers in a `<details><summary>Click to reveal answers</summary>...</details>` block.
    6. **Quick-Reference Glossary**: Include a `## Quick-Reference Glossary` two-column table of essential terms and definitions.
    7. **Expansion Cue**: Close with `**Topics to expand next:** ...` suggesting the next logical subtopic to study.
    8. Use ONLY the retrieved course material for facts; if the material doesn't cover the topic at
       all, do not silently fall back to general knowledge — use the standard "not found in material"
       rule instead of producing generic notes.
    9. This format must render as clean, valid Markdown only (no page citations) since
       it is rendered directly in the chat UI's Markdown viewer and also offered as a downloadable
       `.md` file as-is.
  - If the plan flags multiple sub_questions (a compound question), answer each sub-question in its own
    clearly labeled section (bold sub-heading per sub-question) rather than blending them into one block.
- **RESPONSE SIZING & STUDENT-CENTRIC SIMPLICITY (HARD LIMITS)**:
  - **DEFAULT IS SMALL AND SIMPLE**: Unless the student explicitly used a word like "big", "medium",
    "detailed", "in depth", or "all the X", a default `conceptual`/`diagram`/`list` reply is capped at:
    the hook (1-2 sentences) + Key Topics (3-4 bullets max, one line each) + definition (2-4 sentences)
    + ONE example + the closing question. That is the whole reply — roughly 120-180 words of prose,
    not counting a formula block or a single optional diagram/table.
  - **DO NOT enumerate every sub-type, variant, or kernel/algorithm/formula that exists for a topic
    by default.** If a concept has several variants (e.g. kernel types, distance metrics, activation
    functions), name that variants exist in one sentence and offer to go through them via the closing
    question — do not list and explain each one unless the student specifically asked for "all types"
    or "every kernel" etc.
  - **DO NOT include the full mathematical derivation or objective function by default** for a
    conceptual/intuition-style question ("what is X", "explain X simply"). Only include the formal
    formula block when the student's question is itself about the math/formula, or in `study_notes`
    format, or after the student confirms they want the deeper version via the closing question.
  - If the student explicitly specifies "medium" or "big" or "detailed", scale the response depth
    accordingly — the caps above no longer apply, but the structure (hook → key topics → definition →
    example → closing question) still does.
- **THE CLOSING FOLLOW-UP QUESTION IS MANDATORY, NO EXCEPTIONS**: Every single reply that explains, defines, compares, or lists something — including a reply where you fell back to general academic knowledge because no course material has been uploaded to this workspace — MUST end with one natural, conversational, yes/no-answerable follow-up question. If you add a disclaimer note (e.g. "no documents are currently uploaded, this is based on general academic principles"), the follow-up question comes AFTER that note, not instead of it. The only replies allowed to skip it are: a bare greeting, a "not found in your uploaded material" refusal, or a quiz evaluation that is itself immediately followed by the next question.
- **NEVER END WITH A MULTI-OPTION "HOW TO PROCEED" BLOCK.** Do not write endings like "How to proceed:
  If you have a document... If you want to explore a topic... How would you like to proceed?" with
  multiple bolded branches. That is not a yes/no question and breaks the interaction loop. Collapse it
  into exactly ONE concrete, single-answer closing question instead (pick the single most likely next
  step and offer that; the student can always redirect if it's the wrong guess).
- **GENERAL-KNOWLEDGE FALLBACK (no material uploaded to this session at all)**: If there is no retrieved context AND no course material has ever been uploaded to this session (as opposed to material existing but not covering this specific query — see the "UNKNOWN ANSWER" rules below), you may explain using general academic knowledge. When you do, still follow the full response_format structure above (hook, key topics, definition, example) and add one italic closing note such as *"Note: no course material is uploaded to this workspace yet, so this explanation uses general academic knowledge — upload your textbook or notes for answers grounded in your own material."* followed immediately by the mandatory follow-up question.
- **DIFFERENCES & COMPARISONS (TEXT + TABLE)**:
  - Whenever the student asks for a difference, comparison ("X vs Y"), contrast, or trade-offs:
    1. Provide a short, direct text explanation highlighting the key distinction in simple terms.
    2. Provide a clean, structured **Markdown Comparison Table** (`| Feature / Dimension | {Concept A} | {Concept B} |`) contrasting the core mechanisms.
- **ZERO EMOJIS & PROFESSIONAL TONE**: Strictly NO emojis anywhere in the response (no 📌, 💡, ⚠️, 🚀, etc.). Maintain a clean, professional, academic, yet encouraging tone.
- **NO UNSOLICITED EXAM TRAPS / PITFALLS**: Do not include "Common Pitfalls & Exam Traps" sections unless specifically requested by the student.
- **MATHEMATICAL EQUATIONS & FORMULAS**: Always put core mathematical equations, laws, and algebraic formulas in standalone block math `$$ ... $$` so they automatically render inside a dedicated, highlighted formula box for the student. For inline math within sentences or tables, you MUST use a single `$` sign on each side (e.g., `$ \mathbf{w} $` or `$ M = \frac{2}{||\mathbf{w}||} $`). NEVER use raw parentheses like `( \mathbf{w} )` or `\( ... \)` for math.
- **DO NOT INCLUDE PAGE NUMBERS OR PAGE CITATIONS** (e.g. never write "(p. 50)", "(p. 4)", or "on page 12"). Keep explanations clean and seamless without page citations.
- **NEVER OUTPUT LITERAL LABELS LIKE "HOOK:", "DEFINITION:", "BREAKDOWN:", "VISUAL:", "CLOSE:" AS TEXT.** Write in natural, clean, beautifully formatted Markdown.

CRITICAL MATERIAL GROUNDING & "UNKNOWN ANSWER" RULES:
1. **STRICTLY BASE RESPONSES ON RETRIEVED MATERIAL**: All explanations, examples, definitions, and quizzes MUST be grounded strictly in the student's uploaded course material and retrieved chunks. DO NOT include any out-of-scope, external, or hallucinated information. If a topic is only partially covered in the material, ONLY explain the parts that are explicitly present in the text. Do not add outside knowledge.
2. **WHEN THE ANSWER IS NOT FOUND IN THE PDF / UNKNOWN**:
   - If the student's question is NOT answered in the retrieved course material or you cannot find sufficient information in the PDF:
     - **Do NOT guess, invent, or hallucinate an answer.**
     - **Explicitly tell the student**: "I could not find the answer to this in your uploaded PDF."
     - **Prompt the student**: "Please ask questions specifically related to the concepts and chapters in your uploaded material for **{Subject}** (e.g. {List of available syllabus topics})."
3. **NEVER MISTAKE A CONCEPTUAL QUESTION FOR A SUBJECT TITLE**: If the user asks a question like "what is the type of forest in india", "how does SVM work", or "explain photosynthesis", NEVER treat it as a subject name or say "Understood. Let's study what is the type of forest in india". Answer the question directly using the document context, or state that it is not in the uploaded material.
4. Match tone to an expert peer mentor: warm, articulate, clear, and direct. No emojis.
5. **NEVER HALLUCINATE THE PREVIOUS CONVERSATION**: If the student asks about what you previously
   explained, said, taught, or covered earlier in this session ("what did you just say about X",
   "go back to the previous topic", "what was that module about", "explain the above again"), you
   MUST base your answer strictly on the actual CONVERSATION HISTORY messages provided to you below —
   never invent or reconstruct what an earlier turn "probably" said. If the conversation history
   provided does not actually contain what the student is asking about, say plainly that you don't
   have that earlier turn in this session rather than fabricating a plausible-sounding recap.

INTENT HANDLING & INTERACTIVE CONVERSATION RULES:
1. GREETING / INITIAL TURN: If the user says "Hi", "Hello", "Hey" or begins a session -> intent: "GREETING", extracted_subject: null, is_explanation: false, reply: Greet the student warmly and ask: "Hello! Welcome to IndieTutor. What subject or concept would you like to master today? You can type a topic or attach your syllabus/textbook PDF anytime using the clip below."
2. SUBJECT_SPECIFIED: When the user names a subject or broad topic (e.g. "machine learning", "geography", "linear algebra") -> intent: "SUBJECT_SPECIFIED", extracted_subject: "Proper Subject Name (e.g. Machine Learning)", is_explanation: false, reply: "Understood! Let's focus on **{Subject}**.\n\nYou can attach your textbook or syllabus PDF using the attachment clip below to extract your study plan, or ask any conceptual question to begin!"
3. YES / NO CONFIRMATIONS:
   - When the user answers "yes", "yeah", "sure", "yep", "ok", or "please do" following your previous follow-up question:
     - Look at the previous turn. If you asked *"Shall we do a quick quiz?"*, start the quiz (Question 1 of N). If you asked *"Would you like to see a concrete example / deep-dive?"*, provide that detailed example or explanation directly.
   - When the user answers "no", "nope", "not now":
     - Warmly acknowledge (e.g., *"No problem! What other concept or topic would you like to explore next?"*) and wait for their direction.
   - **COMPOUND CONFIRMATIONS — MANDATORY, NO EXCEPTIONS**: If the message contains MORE than
     the bare yes/no — i.e. it also asks a new question or adds new content in the same message
     (e.g. "yes, and is this used for self attention", "sure, but how is this different from X")
     — you MUST do BOTH, not just one:
       (a) act on the previous offer as instructed above, AND
       (b) directly and completely answer the additional question, in its own clearly labeled
           section using the retrieved context.
     A leading "yes" is never a reason to drop, shorten, or silently skip the rest of what the
     student wrote in the same message. If a "COMPOUND MESSAGE" system note appears below with
     both a confirmed offer and a new question, treat answering the new question as equally
     mandatory as the closing-follow-up-question rule elsewhere in this prompt.
4. QUIZ / QUESTION MODE (CRITICAL ONE-BY-ONE RULE):
   - When the student asks to be tested or asked questions (e.g. "ask me 2 questions", "quiz me with 3 questions"):
   - When the student replies with an answer (e.g. selects an option or explains):
     - Check the previous question number from conversation history.
     - **If answering Question K where K < total_questions (e.g. answering Question 1 of 2):**
       - Evaluate their answer in `"reply"` (e.g. "Spot on! Option B is correct because...").
       - Populate `quiz_data` with the NEXT question: `{"question_number": K + 1, "total_questions": N, "question_text": "...", "options": [...], "correct_option": "...", "evaluation": "...", "is_completed": false}`.
     - **If answering the FINAL question where K == total_questions (e.g. answering Question 2 of 2):**
       - **DO NOT GENERATE ANOTHER QUESTION.**
       - In `"reply"`, evaluate their final answer, declare the quiz complete, and provide a 1-sentence mastery summary (e.g. "Great job! You have completed the 2-question quiz on {Topic}.").
       - Set `"quiz_data": null` (or `"quiz_data": {"question_number": N, "total_questions": N, "question_text": "", "options": [], "is_completed": true, "evaluation": "Your final evaluation here"}`).
4. QUESTION / EXPLANATION: When the user asks a specific conceptual question (e.g. "What is an LLM?", "Explain how transformers work", "Parts of a circle in bullet points") -> intent: "QUESTION", is_explanation: true, reply: Provide the tailored, well-structured explanation according to the guidelines above.

JSON SCHEMA:
{
  "thought_process": "Brief 1-2 sentence internal reasoning analyzing the query, context, and formatting choice.",
  "intent": "GREETING" | "SUBJECT_SPECIFIED" | "QUESTION" | "QUIZ_QUESTION" | "EVALUATE_AND_NEXT_QUESTION",
  "extracted_subject": "string or null",
  "is_explanation": true | false,
  "quiz_data": {
    "question_number": 1,
    "total_questions": 5,
    "question_text": "Question text here",
    "options": ["A) Option 1", "B) Option 2", "C) Option 3", "D) Option 4"],
    "correct_option": "A",
    "evaluation": "Evaluation of previous answer if answering, otherwise null",
    "is_completed": false
  } | null,
  "reply": "Clean Markdown formatted text of the question or answer evaluation",
  "response_format": "conceptual" | "comparison" | "list" | "diagram" | "quiz" | "study_plan" | "study_notes",
  "export_ready": true | false,
  "groundedness_note": "1 short sentence: which parts of the reply are directly supported by retrieved context vs general knowledge, or 'not found in material' if applicable"
}
Respond with ONLY this JSON object, no preamble, no markdown fences.
"""

    VERIFIER_SYSTEM_PROMPT = """You are a strict fact-checking and completeness verifier for an academic tutoring system.
You will be given the STUDENT'S QUESTION, RETRIEVED COURSE MATERIAL, and a DRAFT ANSWER produced from it.
Check two independent things:

1. GROUNDING: Are the draft's specific factual claims (definitions, numbers, named mechanisms, examples)
   actually supported by the retrieved material, or does the model appear to have invented content not
   present in the material?
   - Pay special attention to any COMPARISON TABLE in the draft. Check EACH row/cell individually against
     the material, not just the table's general topic. Claims about relative performance, computational
     complexity/cost, or which approach is "better"/"superior" are a common place for models to invent a
     plausible-sounding claim that isn't actually stated in (or is contradicted by) the material — verify
     these specifically rather than assuming a well-formatted table is accurate.

2. COMPLETENESS: Does the draft address EVERY distinct question or request in the student's message?
   - If the student's message contains a confirmation ("yes"/"no") FOLLOWED BY an additional question in
     the same message, the draft must answer both — acting on the confirmed offer is not a substitute for
     answering the appended question. A draft that only handles the confirmation and ignores or glosses
     over an appended question is INCOMPLETE, even if everything it does say is well-grounded.
   - If the student's message has multiple sub-questions, each one must be addressed; missing any one
     of them makes the draft incomplete.

Respond with ONLY this JSON object:
{
  "grounded": true | false,
  "issue": "short description of the unsupported/fabricated claim if grounded is false, else null",
  "complete": true | false,
  "missing": "short description of what part of the student's message was not addressed if complete is false, else null"
}
"""

    def __init__(self, max_retries: int = 1, enable_self_critique: bool = True):
        self.max_retries = max_retries
        self.enable_self_critique = enable_self_critique

    async def analyze_and_respond(
        self,
        message: str,
        current_subject: Optional[str] = None,
        history: Optional[List[Dict[str, str]]] = None,
        context: Optional[str] = None,
        file_name: Optional[str] = None,
        doc_status_note: Optional[str] = None,
        user_id: str = "default_user",
        user_name: Optional[str] = None,
        difficulty: str = "standard",
        query_analysis: Optional[Dict[str, Any]] = None,
        pending_followup: Optional[Dict[str, Any]] = None,
        has_uploaded_material: Optional[bool] = None,
    ) -> Dict[str, Any]:
        """
        Executes the plan produced by QueryAnalyzerAgent: builds a plan-aware prompt,
        generates a grounded response with retry-on-malformed-JSON, optionally
        self-verifies groundedness against the retrieved context, and returns a
        structured result. Never raises — always degrades to a heuristic fallback.

        pending_followup: the same dict this agent returned as `result["pending_followup"]`
        on the previous turn (persisted by the caller). QueryAnalyzerAgent already
        resolves plain yes/no replies against it into a concrete `recommended_action`,
        but we also surface it here as an explicit system note so any *non-boolean*
        follow-up ("yeah go ahead and quiz me on that") still gets a precise prior
        instead of the LLM re-reading raw history.
        has_uploaded_material: whether the session has ANY document uploaded at all.
        Pass this explicitly — don't infer it from `context` being empty, since that's
        also true when material exists but simply doesn't cover this particular query.
        The two cases get different handling (general-knowledge fallback vs. strict
        "not found in your material" refusal).
        """
        # Trigger non-blocking background memory extraction as early as possible.
        asyncio.create_task(user_memory_store.auto_extract_and_update(user_id, message, history))

        # ─── Deterministic short-circuit: topic confirmed absent from the material ───
        # QueryAnalyzerAgent already fuzzy-matched the target topic against the
        # session's known curriculum index (when one was supplied) and set this
        # action if there was no match. Answering it here, without a generation
        # call, makes the "never guess outside the material" rule unconditional
        # instead of merely prompted-for.
        if query_analysis and query_analysis.get("recommended_action") == "NOT_IN_MATERIAL":
            return self._not_in_material_response(query_analysis, current_subject)

        base_messages = self._build_base_messages(
            current_subject, doc_status_note, context, file_name,
            difficulty, user_id, query_analysis, history, pending_followup,
            has_uploaded_material, message=message,
        )

        result: Optional[Dict[str, Any]] = None
        last_error: Optional[Exception] = None

        for attempt in range(self.max_retries + 1):
            try:
                messages = list(base_messages)
                if attempt > 0:
                    messages.append({
                        "role": "system",
                        "content": "Your previous response was not valid JSON or was missing the 'reply' "
                                    "field. Respond again with ONLY the raw JSON object, no prose, no fences.",
                    })
                messages.append({"role": "user", "content": f"Student's question: {message}"})

                raw = await llm_client.chat(messages, temperature=0.2 if attempt == 0 else 0.0)
                parsed = self._parse_llm_response(raw)
                if parsed and parsed.get("reply"):
                    result = parsed
                    break
            except Exception as e:  # noqa: BLE001 - degrade, never crash the request
                last_error = e
                print(f"[DecisionAgent] generation attempt {attempt} failed: {e}")
            if attempt < self.max_retries:
                await asyncio.sleep(0.3 * (attempt + 1))

        if result is None:
            if last_error:
                print(f"[DecisionAgent] all generation attempts exhausted, using fallback: {last_error}")
            return self._fallback_response(message, context, current_subject, query_analysis)

        result = self._finalize(result, message)

        if (
            self.enable_self_critique
            and result.get("is_explanation")
            and context
            and context.strip()
            and len(result.get("reply", "")) > 40
        ):
            result = await self._maybe_reground(result, context, message)

        return result

    # ------------------------------------------------------------------
    # Prompt construction
    # ------------------------------------------------------------------

    def _build_base_messages(
        self,
        current_subject: Optional[str],
        doc_status_note: Optional[str],
        context: Optional[str],
        file_name: Optional[str],
        difficulty: str,
        user_id: str,
        query_analysis: Optional[Dict[str, Any]],
        history: Optional[List[Dict[str, str]]],
        pending_followup: Optional[Dict[str, Any]] = None,
        has_uploaded_material: Optional[bool] = None,
        message: Optional[str] = None,
    ) -> List[Dict[str, str]]:
        messages = [{"role": "system", "content": self.SYSTEM_PROMPT}]

        raw_msg = (message or "").lower()
        has_explicit_visual = bool(re.search(
            r"\b(figure|diagram|image|photo|picture|flowchart|illustration|visual|draw|with a figure|with an image|with image|with figure|with photo|with picture|show figure|draw figure|show image|draw image)\b",
            raw_msg
        ))
        is_visual_query = bool(
            has_explicit_visual
            or (query_analysis and (query_analysis.get("requires_image_data") or query_analysis.get("response_format") == "diagram"))
        )
        if is_visual_query and query_analysis:
            query_analysis["response_format"] = "diagram"
            query_analysis["requires_image_data"] = True

        if is_visual_query:
            messages.append({
                "role": "system",
                "content": (
                    "CRITICAL VISUAL GENERATION REQUIREMENT:\n"
                    "The student requested a figure, diagram, image, or visual illustration.\n"
                    "1. You MUST generate an actual inline visual in a fenced ```svg code block (or ```mermaid for simple linear flows).\n"
                    "2. STRICTLY FORBIDDEN: DO NOT merely write a text description or breakdown of a figure (e.g., NEVER write 'Figure 4 Breakdown: Panel (a)...' in plain text without the actual rendered SVG diagram). If the retrieved textbook context mentions a figure or diagram (like 'Figure 4'), you MUST TRANSLATE IT INTO AN ACTUAL RENDERABLE <svg>...</svg> CODE BLOCK so it renders on the student's screen.\n"
                    "3. Make the SVG clean, colorful, with a viewBox attribute (e.g. viewBox=\"0 0 700 400\"), rounded rects, clear text labels, and colored markers."
                ),
            })

        if query_analysis:
            plan_note = self._format_plan_note(query_analysis)
            messages.append({
                "role": "system",
                "content": f"PLANNING NOTE FROM UPSTREAM AGENT:\n{plan_note}\n"
                            "Use this to choose response_format and to check off each sub-question, "
                            "but re-verify every claim against the retrieved context below.",
            })

        if pending_followup:
            confirmed_followup = (query_analysis or {}).get("confirmed_followup")
            resolved = bool((query_analysis or {}).get("resolved_from_followup"))

            if confirmed_followup:
                # Compound message: the planner detected — structurally, not just via
                # prompt-following — that this message both confirms/declines the prior
                # offer AND carries additional new content. This is the exact pattern
                # that previously produced an answer covering only the confirmed offer
                # (e.g. multi-head projection matrices) while silently dropping an
                # appended question (e.g. "is this used for self attention").
                verb = "confirmed" if confirmed_followup.get("is_affirmation") else "declined"
                messages.append({
                    "role": "system",
                    "content": (
                        "COMPOUND MESSAGE — TWO THINGS ARE REQUIRED IN THIS REPLY, NOT JUST ONE:\n"
                        f"1) The student {verb} your previous offer: {json.dumps(pending_followup)}. "
                        "Act on it as instructed in the YES/NO CONFIRMATIONS rule above.\n"
                        "2) The SAME message also contains new content beyond that confirmation — see "
                        "the PLANNING NOTE's sub_questions / target_topic above for what it is. Answer "
                        "that new content directly and completely, in its own clearly labeled section, "
                        "using the retrieved context. Do not let step 1 cause you to shorten, omit, or "
                        "merge away step 2 — both parts are mandatory."
                    ),
                })
            elif resolved:
                messages.append({
                    "role": "system",
                    "content": (
                        "EXPLICIT FOLLOW-UP CONTEXT: last turn you closed with this offer: "
                        f"{json.dumps(pending_followup)}. "
                        "The student's message is a direct reply to it — do not re-derive what the offer "
                        "was from raw chat history, act on it directly (e.g. a 'quiz_offer' means start "
                        "Question 1 now; a 'next_question' means the message is the student's literal "
                        "answer to the in-progress question, not a new topic)."
                    ),
                })
            else:
                messages.append({
                    "role": "system",
                    "content": (
                        "EXPLICIT FOLLOW-UP CONTEXT: last turn you closed with this offer: "
                        f"{json.dumps(pending_followup)}. "
                        "If the student's message refers back to 'this'/'that'/'it' without naming a new "
                        "topic, it means the topic above ('target_topic' in the JSON), not whatever "
                        "'Current Active Subject' happens to be set to and not a new topic you invent — "
                        "e.g. a request to simplify/shorten/bullet-point 'this' means simplify that exact "
                        "target_topic, nothing else."
                    ),
                })

        if difficulty == "easier":
            messages.append({
                "role": "system",
                "content": (
                    "DIFFICULTY LEVEL: SIMPLIFIED / EASIER\n"
                    "- Use intuitive real-world analogies; minimize technical jargon.\n"
                    "- Provide concise breakdown points (max 2).\n"
                    "- Do NOT include page numbers.\n"
                    "- Keep recall question simple and concrete.\n"
                    "- Do NOT say 'here is the simpler version' — answer directly at the easier level."
                )
            })

        memory_str = user_memory_store.format_memory_for_prompt(user_id)
        if memory_str:
            messages.append({"role": "system", "content": f"STUDENT LEARNING PROFILE & MEMORY:\n{memory_str}"})

        if current_subject:
            messages.append({"role": "system", "content": f"Current Active Subject: {current_subject}"})

        if doc_status_note:
            messages.append({"role": "system", "content": f"DOCUMENT PROCESSING STATUS: {doc_status_note}"})

        if context and context.strip():
            doc_label = f"from '{file_name}'" if file_name else "from uploaded document"
            messages.append({
                "role": "system",
                "content": f"RETRIEVED CONTEXT CHUNKS ({doc_label}):\n\n{context.strip()}\n\n"
                            "STRICT INSTRUCTION: Ground your answer ONLY in the uploaded course material above. "
                            "If the student asks something outside this material (e.g. unrelated coding, general "
                            "chatbot queries), politely decline and redirect them back to their syllabus topics.",
            })
        elif query_analysis and query_analysis.get("intent") == "MATERIAL_TOPICS_REQUEST":
            messages.append({
                "role": "system",
                "content": "NOTE: The student asked for the curriculum topics covered in their material, but no document context was provided. "
                            "Politely explain that no course material has been uploaded to this session yet, and invite them to upload their textbook or notes PDF using the attachment button so you can extract the curriculum roadmap for them.",
            })
        elif has_uploaded_material is False:
            # Distinct from "material exists but nothing retrieved for this query": here
            # there is nothing in the session to retrieve from at all, so the
            # GENERAL-KNOWLEDGE FALLBACK rule in the SYSTEM_PROMPT applies instead of
            # the strict refusal rule.
            messages.append({
                "role": "system",
                "content": (
                    "NOTE: No course material has been uploaded to this session at all (there is "
                    "nothing to retrieve from — this is not the same as 'material exists but doesn't "
                    "cover this'). Apply the GENERAL-KNOWLEDGE FALLBACK rule: answer from general "
                    "academic knowledge, keep the full response_format structure (hook, key topics, "
                    "definition, example), add the required italic disclaimer note, and still end with "
                    "the mandatory closing follow-up question after that note."
                ),
            })
        else:
            # has_uploaded_material is True, or unknown — default to the strict rule
            # rather than letting the model decide whether to improvise from general
            # knowledge. This fires for every empty-context turn now, not just when the
            # planner explicitly said "EXPLAIN", so ambiguity can no longer fall through
            # ungoverned.
            messages.append({
                "role": "system",
                "content": "NOTE: No matching context was retrieved from the uploaded material for this query. "
                            "Follow the 'UNKNOWN ANSWER' rule — say the material doesn't cover it rather than guessing.",
            })

        if history:
            for h in history[-6:]:
                messages.append({"role": h.get("role", "user"), "content": h.get("content", "")})

        if query_analysis and query_analysis.get("recommended_action") == "RECALL_HISTORY":
            last_turn = self._extract_last_assistant_turn(history)
            if last_turn:
                messages.append({
                    "role": "system",
                    "content": (
                        "STRICT GROUNDING FOR THIS TURN: the student is asking about what you said/covered "
                        "earlier in THIS session. Here is your own most recent prior reply, verbatim:\n\n"
                        f"{last_turn[:2000]}\n\n"
                        "Base your answer ONLY on the text above (and any other conversation-history messages "
                        "included in this prompt). Do NOT invent or embellish anything about earlier turns "
                        "that isn't actually present in that text."
                    ),
                })
            else:
                messages.append({
                    "role": "system",
                    "content": (
                        "STRICT GROUNDING FOR THIS TURN: the student is asking about an earlier turn in this "
                        "session, but no prior assistant reply is present in the conversation history provided "
                        "to you. Say plainly that you don't have an earlier turn to refer back to in this "
                        "session, rather than inventing a recap."
                    ),
                })

        return messages

    @staticmethod
    def _extract_last_assistant_turn(history: Optional[List[Dict[str, str]]]) -> Optional[str]:
        """Finds the most recent assistant/model message in the raw history, so a
        meta-referential question ('what did you just say') can be grounded in the
        actual text of that turn instead of the model reconstructing it from memory."""
        if not history:
            return None
        for h in reversed(history):
            role = (h.get("role") or h.get("sender") or "").lower()
            text = (h.get("content") or h.get("text") or h.get("message") or "").strip()
            if role in ("assistant", "model", "bot", "ai") and text:
                return text
        return None

    @staticmethod
    def _format_plan_note(plan: Dict[str, Any]) -> str:
        parts = [f"- intent: {plan.get('intent')}"]
        if plan.get("target_topic"):
            parts.append(f"- target_topic: {plan.get('target_topic')}")
        topics = plan.get("topics") or []
        if topics:
            parts.append(f"- topics: {json.dumps(topics)}")
        entities = plan.get("entities") or []
        if entities:
            parts.append(f"- technical entities: {json.dumps(entities)}")
        sub_qs = plan.get("sub_questions") or []
        if len(sub_qs) > 1:
            parts.append(f"- decomposed sub-questions: {json.dumps(sub_qs)}")
        if plan.get("response_format"):
            parts.append(f"- recommended response_format: {plan.get('response_format')}")
        retrieval_plan = plan.get("retrieval_plan")
        if retrieval_plan:
            parts.append(f"- retrieval plan: {json.dumps(retrieval_plan)}")
        if plan.get("requires_table_data"):
            parts.append("- likely needs table/numeric data")
        if plan.get("requires_image_data"):
            parts.append("- requires_image_data: true (VISUAL REQUEST: MUST generate an inline ```svg or ```mermaid diagram block)")
        if plan.get("confidence") is not None:
            parts.append(f"- planner confidence: {plan.get('confidence')}")
        status = plan.get("status")
        if status and status != "clear":
            parts.append(f"- query status: {status}")
        if plan.get("needs_clarification") or status in ("ambiguous", "needs_clarification"):
            clarification = plan.get("clarification_prompt")
            if clarification:
                parts.append(f"- clarification suggestion: {clarification}")
            else:
                parts.append("- planner flagged low confidence: if the question is genuinely ambiguous, ask a brief clarifying question instead of guessing")
        if plan.get("reasoning"):
            parts.append(f"- planner reasoning: {plan.get('reasoning')}")
        return "\n".join(parts)

    # ------------------------------------------------------------------
    # Parsing & cleanup
    # ------------------------------------------------------------------

    @staticmethod
    def _strip_code_fences(text: str) -> str:
        cleaned = text.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("\n", 1)[1] if "\n" in cleaned else cleaned[3:]
            if cleaned.endswith("```"):
                cleaned = cleaned.rsplit("```", 1)[0]
            if cleaned.lower().startswith("json"):
                cleaned = cleaned[4:].strip()
        return cleaned.strip()

    def _parse_llm_response(self, raw: str) -> Optional[Dict[str, Any]]:
        cleaned = self._strip_code_fences(raw)
        data = None

        if "{" in cleaned and "}" in cleaned:
            start_idx, end_idx = cleaned.find("{"), cleaned.rfind("}")
            json_str = cleaned[start_idx:end_idx + 1]
            try:
                data = json.loads(json_str, strict=False)
            except Exception:
                reply_match = re.search(r'"reply"\s*:\s*"((?:\\.|[^"\\])*)"', json_str, re.DOTALL)
                thought_match = re.search(r'"thought_process"\s*:\s*"((?:\\.|[^"\\])*)"', json_str, re.DOTALL)
                if reply_match:
                    raw_reply = reply_match.group(1).encode().decode("unicode_escape", "ignore")
                    raw_thought = (
                        thought_match.group(1).encode().decode("unicode_escape", "ignore")
                        if thought_match else ""
                    )
                    data = {"reply": raw_reply, "thought_process": raw_thought, "is_explanation": True}

        if not data or "reply" not in data or not data.get("reply"):
            if cleaned and "{" not in cleaned:
                # Model returned raw markdown/text without a JSON wrapper — usable as-is.
                data = {"reply": cleaned, "thought_process": "", "is_explanation": True}
            else:
                return None

        return data

    def _finalize(self, data: Dict[str, Any], message: str) -> Dict[str, Any]:
        reply = data.get("reply", "")
        reply = re.sub(r"[\U00010000-\U0010ffff]", "", reply).strip()
        reply = re.sub(r"^(?:HOOK|DEFINITION|BREAKDOWN|VISUAL|CLOSE):\s*", "", reply, flags=re.MULTILINE)
        reply = re.sub(r"\[Source:[^\]]*\]", "", reply)
        reply = re.sub(r"\s*\((?:p\.|pages?)\s*\d+(?:[-–]\d+)?\)", "", reply, flags=re.IGNORECASE)
        reply = re.sub(r"\b(?:on|from|see)\s+pages?\s+\d+(?:[-–]\d+)?\b", "", reply, flags=re.IGNORECASE)
        reply = re.sub(r"\\le\s*ft\b", r"\\left", reply)
        reply = re.sub(r"\\righ\s*t\b", r"\\right", reply)
        reply = re.sub(r"\\sq\s*rt\b", r"\\sqrt", reply)
        reply = re.sub(r"\n{3,}", "\n\n", reply).strip()

        thought = data.get("thought_process") or "Analyzed question against uploaded material and synthesized a clear, simple explanation."
        intent = data.get("intent", "QUESTION")
        is_expl = data.get("is_explanation", True)

        is_question = bool(re.search(
            r"\b(what|how|why|when|where|which|explain|describe|difference|types|summarize|important|concepts)\b|\?",
            message.lower(),
        ))
        if is_question:
            intent = "QUESTION"
            is_expl = True

        extracted_subject = data.get("extracted_subject") if (intent == "SUBJECT_SPECIFIED" and not is_question) else None
        if intent in ("GREETING", "SUBJECT_SPECIFIED"):
            is_expl = False

        result_format = data.get("response_format", "conceptual")
        export_ready = (result_format == "study_notes")
        not_found = "could not find the answer" in reply.lower() or "not found in your uploaded" in reply.lower()
        if not_found:
            export_ready = False

        quiz_data = data.get("quiz_data")
        is_quiz_in_progress = bool(quiz_data and not quiz_data.get("is_completed", False))
        reply, appended_followup = self._ensure_closing_followup(
            reply=reply, intent=intent, result_format=result_format,
            not_found=not_found, is_quiz_in_progress=is_quiz_in_progress,
            extracted_subject=extracted_subject, message=message,
        )

        pending_followup = appended_followup or self._derive_pending_followup(
            intent=intent, result_format=result_format, quiz_data=quiz_data,
            not_found=not_found, extracted_subject=extracted_subject,
        )

        return {
            "thought_process": thought,
            "intent": intent,
            "extracted_subject": extracted_subject,
            "is_explanation": is_expl,
            "quiz_data": quiz_data,
            "reply": reply,
            "groundedness_note": data.get("groundedness_note"),
            "response_format": result_format,
            "export_ready": export_ready,
            # Persist this verbatim and pass it back as `pending_followup` on the
            # next call to QueryAnalyzerAgent.analyze() / DecisionAgent.analyze_and_respond()
            # so a bare "yes"/"no" reply resolves deterministically instead of by
            # re-reading raw chat history.
            "pending_followup": pending_followup,
        }

    @staticmethod
    def _ensure_closing_followup(
        reply: str,
        intent: str,
        result_format: str,
        not_found: bool,
        is_quiz_in_progress: bool,
        extracted_subject: Optional[str],
        message: str,
    ) -> Tuple[str, Optional[Dict[str, Any]]]:
        """Code-level safety net for the SYSTEM_PROMPT's mandatory-closing-question rule.

        The screenshot that motivated this: a general-knowledge-fallback reply ended on
        an italic "no documents uploaded" disclaimer with no question at all — a valid
        way for the LLM to drift even with the prompt instruction in place. Rather than
        rely solely on prompting, we deterministically check whether the reply already
        ends on a question and append a sensible default if it doesn't, so the UI's
        "answer -> yes/no -> next step" loop can never silently break.

        Returns (possibly-modified reply, a pending_followup dict if we appended one
        else None — None means the caller should fall back to `_derive_pending_followup`
        because the model's own closing question is presumably already correct).
        """
        skip = (
            not_found
            or is_quiz_in_progress  # quiz evaluation already carries its own next question
            or intent in ("GREETING", "SUBJECT_SPECIFIED")
            or not reply.strip()
        )
        if skip:
            return reply, None

        # A closing question is any of the last ~3 non-empty lines ending in "?".
        tail_lines = [ln for ln in reply.strip().splitlines() if ln.strip()][-3:]
        already_has_question = any(ln.strip().endswith("?") for ln in tail_lines)
        if already_has_question:
            return reply, None

        topic_label = extracted_subject or "this topic"
        if result_format == "material_topics":
            question = "Would you like to start with the first topic, or is there a specific one you'd like to explore first?"
            followup = {"type": "topic_selection"}
        elif result_format in ("comparison", "diagram"):
            question = f"Would you like to see a concrete step-by-step example of this in **{topic_label}**?"
            followup = {"type": "example_or_deepdive", "target_topic": extracted_subject}
        else:
            question = f"Would you like to try a quick 2-question quiz on **{topic_label}** to check your understanding?"
            followup = {"type": "quiz_offer", "target_topic": extracted_subject}

        separator = "\n\n" if not reply.endswith("\n") else "\n"
        return f"{reply}{separator}{question}", followup

    @staticmethod
    def _derive_pending_followup(
        intent: str,
        result_format: str,
        quiz_data: Optional[Dict[str, Any]],
        not_found: bool,
        extracted_subject: Optional[str],
    ) -> Optional[Dict[str, Any]]:
        """Infers what kind of yes/no (or 'answer the question') offer this response just
        made, purely from information already computed for this turn — no extra LLM call.
        This is the write-side of the follow-up contract QueryAnalyzerAgent consumes."""
        if not_found:
            return None
        if quiz_data and not quiz_data.get("is_completed", False):
            return {
                "type": "next_question",
                "question_number": quiz_data.get("question_number"),
                "total_questions": quiz_data.get("total_questions"),
            }
        if result_format == "material_topics":
            return {"type": "topic_selection"}
        if intent in ("GREETING", "SUBJECT_SPECIFIED"):
            return None
        if result_format in ("conceptual", "diagram", "list", "comparison"):
            # These formats always close with a yes/no offer per SYSTEM_PROMPT's
            # RESPONSE GUIDELINES (either "see an example / deep dive" or "quick quiz").
            return {"type": "example_or_deepdive", "target_topic": extracted_subject}
        return None

    # ------------------------------------------------------------------
    # Self-verification pass
    # ------------------------------------------------------------------

    async def _maybe_reground(
        self, result: Dict[str, Any], context: str, message: str,
    ) -> Dict[str, Any]:
        """Runs a cheap second LLM pass checking both (a) whether the reply's claims are
        supported by the retrieved context, and (b) whether it addressed every distinct
        part of the student's message. Either failure triggers one regeneration with a
        targeted instruction. Any error here is swallowed — verification is a quality
        improvement, not a hard dependency.

        The completeness check exists specifically because a compound message ("yes,
        and is this used for self attention") can produce a draft that is fully grounded
        in everything it says, while still silently never answering half the question —
        a groundedness-only check has no way to catch that."""
        try:
            verdict = await self._verify_groundedness(result["reply"], context, message)
        except Exception as e:  # noqa: BLE001
            print(f"[DecisionAgent] verification skipped due to error: {e}")
            return result

        if verdict is None:
            return result

        is_grounded = verdict.get("grounded", True)
        is_complete = verdict.get("complete", True)
        if is_grounded and is_complete:
            return result

        problems = []
        if not is_grounded:
            problems.append(f"unsupported/fabricated claim: {verdict.get('issue')}")
        if not is_complete:
            problems.append(f"incomplete — missing: {verdict.get('missing')}")
        print(f"[DecisionAgent] verification flagged issues, regenerating once: {'; '.join(problems)}")

        try:
            instruction_parts = [
                "A verification pass found the following issue(s) with a prior draft:",
                *[f"- {p}" for p in problems],
                "Regenerate the answer using ONLY facts present in the retrieved context below.",
            ]
            if not is_grounded:
                instruction_parts.append(
                    "If the material genuinely doesn't cover a point, say so explicitly rather than "
                    "restating the unsupported claim — this applies to comparison-table cells too."
                )
            if not is_complete:
                instruction_parts.append(
                    "Make sure this version explicitly answers EVERY distinct question in the "
                    "student's message, including anything appended after a yes/no confirmation."
                )
            messages = [
                {"role": "system", "content": self.SYSTEM_PROMPT},
                {"role": "system", "content": "\n".join(instruction_parts)},
                {
                    "role": "system",
                    "content": f"RETRIEVED CONTEXT CHUNKS:\n\n{context.strip()}",
                },
                {"role": "user", "content": f"Student's question: {message}"},
            ]
            raw = await llm_client.chat(messages, temperature=0.0)
            parsed = self._parse_llm_response(raw)
            if parsed and parsed.get("reply"):
                return self._finalize(parsed, message)
        except Exception as e:  # noqa: BLE001
            print(f"[DecisionAgent] regeneration attempt failed, keeping original reply: {e}")

        return result

    async def _verify_groundedness(self, reply: str, context: str, message: str) -> Optional[Dict[str, Any]]:
        messages = [
            {"role": "system", "content": self.VERIFIER_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    f"STUDENT'S QUESTION:\n{message}\n\n"
                    f"RETRIEVED COURSE MATERIAL:\n{context.strip()[:4000]}\n\n"
                    f"DRAFT ANSWER:\n{reply}"
                ),
            },
        ]
        raw = await llm_client.chat(messages, temperature=0.0)
        cleaned = self._strip_code_fences(raw)
        if "{" not in cleaned or "}" not in cleaned:
            return None
        start, end = cleaned.find("{"), cleaned.rfind("}")
        try:
            return json.loads(cleaned[start:end + 1], strict=False)
        except Exception:
            return None

    # ------------------------------------------------------------------
    # Deterministic intent responses (no LLM call)
    # ------------------------------------------------------------------

    def _not_in_material_response(
        self, query_analysis: Dict[str, Any], current_subject: Optional[str],
    ) -> Dict[str, Any]:
        """Deterministic answer for a topic QueryAnalyzerAgent confirmed is absent from
        the session's known material index — enforces rule #2 ("never guess") without
        depending on the LLM to comply, and skips a generation call entirely."""
        target = query_analysis.get("target_topic") or current_subject or "that topic"
        subject_label = current_subject or "your uploaded material"
        reply = (
            f"I could not find **{target}** in your uploaded PDF.\n\n"
            f"Please ask questions specifically related to the concepts and chapters covered in "
            f"{subject_label}."
        )
        return {
            "thought_process": f"Planner confirmed '{target}' does not match the session's known material topics; answered deterministically without a generation call.",
            "intent": query_analysis.get("intent", "QUESTION"),
            "extracted_subject": None,
            "is_explanation": False,
            "quiz_data": None,
            "reply": reply,
            "groundedness_note": "Not answered — topic confirmed outside the uploaded material.",
            "response_format": "conceptual",
            "export_ready": False,
            "pending_followup": None,
        }

    def _greeting_response(self) -> Dict[str, Any]:
        """Bare greeting, confirmed by the planner's fast-path heuristic.
        Answered directly — no retrieval, no generation call, so there's no
        retrieved context around to tempt the model into the wrong branch.
        """
        return {
            "thought_process": "Message is a bare greeting; answered directly without invoking retrieval or generation.",
            "intent": "GREETING",
            "extracted_subject": None,
            "is_explanation": False,
            "quiz_data": None,
            "reply": (
                "Hello! Welcome to IndieTutor. What subject or concept would you like to master today? "
                "You can type a topic or attach your syllabus/textbook PDF anytime using the clip below."
            ),
            "groundedness_note": None,
            "response_format": "conceptual",
            "export_ready": False,
            "pending_followup": None,
        }

    # ------------------------------------------------------------------
    # Deterministic fallback (used only if the LLM is unreachable)
    # ------------------------------------------------------------------

    def _fallback_response(
        self,
        message: str,
        context: Optional[str],
        current_subject: Optional[str],
        query_analysis: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        # Handle study notes fallback explicitly
        if query_analysis and (query_analysis.get("intent") == "STUDY_NOTES_REQUEST" or query_analysis.get("response_format") == "study_notes"):
            target = query_analysis.get("target_topic") or current_subject or "this topic"
            return {
                "thought_process": f"LLM unavailable; failed to generate structured study notes for {target}.",
                "intent": "STUDY_NOTES_REQUEST",
                "extracted_subject": None,
                "is_explanation": True,
                "quiz_data": None,
                "reply": f"I couldn't reach the reasoning engine to generate study notes for **{target}** just now. Please verify your connection or try again in a moment.",
                "groundedness_note": "Notes generation fallback; LLM unreachable.",
                "response_format": "study_notes",
                "export_ready": False,
                "pending_followup": None,
            }

        lower = message.lower().strip()
        is_greeting = bool(re.search(r"\b(hi|hello|hey|good morning|good evening|greetings)\b", lower))

        if is_greeting and not any(
            kw in lower for kw in
            ["learn", "study", "exam", "help", "rows", "columns", "what", "how", "why", "table", "forest", "concept", "tree"]
        ):
            return {
                "thought_process": "Student greeted. Prompting them to choose a study subject or topic.",
                "intent": "GREETING",
                "extracted_subject": None,
                "is_explanation": False,
                "quiz_data": None,
                "reply": "Hello! Welcome to DeepTutor. What subject or concept would you like to explore today?",
                "groundedness_note": None,
                "pending_followup": None,
            }

        if context:
            clean_ctx = re.sub(r"\[Source:[^\]]*\]", "", context)
            clean_ctx = re.sub(r"\s*\((?:p\.|pages?)\s*\d+(?:[-–]\d+)?\)", "", clean_ctx)
            clean_ctx = re.sub(r"\s+", " ", clean_ctx).strip()
            sentences = [s.strip() for s in re.split(r"\. |\.\n", clean_ctx) if len(s.strip()) > 15][:3]
            summary_text = ". ".join(sentences) + "." if sentences else clean_ctx[:300]
            return {
                "thought_process": "LLM unavailable; extracted foundational definition directly from retrieved material.",
                "intent": "QUESTION",
                "extracted_subject": None,
                "is_explanation": True,
                "quiz_data": None,
                "reply": f"{summary_text}\n\n**Key Takeaway:** Focus on how this principle applies to your problem solving.\n\n**Quick check:** Would you like a practice quiz question on this topic?",
                "groundedness_note": "Directly extracted from retrieved context; not LLM-synthesized.",
                "pending_followup": {"type": "quiz_offer", "target_topic": current_subject},
            }

        if query_analysis and query_analysis.get("intent") == "MATERIAL_TOPICS_REQUEST":
            return {
                "thought_process": "Student requested topics for the material, but LLM is unreachable or material is not uploaded.",
                "intent": "MATERIAL_TOPICS_REQUEST",
                "extracted_subject": None,
                "is_explanation": True,
                "quiz_data": None,
                "reply": (
                    "No course material has been uploaded to this session yet.\n\n"
                    "To view the curriculum topics, please upload your textbook or notes PDF using the attachment clip below, and I will extract the curriculum topics and create a personalized study roadmap for you."
                ),
                "groundedness_note": None,
                "response_format": "material_topics",
                "export_ready": False,
                "pending_followup": None,
            }

        is_question = any(q in lower for q in [
            "what", "how", "why", "when", "where", "which", "explain", "describe",
            "types", "difference", "compare", "important", "concepts", "?",
        ])
        if is_question:
            target = query_analysis.get("target_topic") if query_analysis else None
            topic_label = target or current_subject or "this topic"
            return {
                "thought_process": f"LLM unavailable; returning a generic structure placeholder for {topic_label}.",
                "intent": "QUESTION",
                "extracted_subject": None,
                "is_explanation": True,
                "quiz_data": None,
                "reply": (
                    f"I couldn't reach the reasoning engine just now, and I don't have retrieved material for "
                    f"**{topic_label}** to ground an answer in. Please try again in a moment, or upload the "
                    f"relevant syllabus/textbook PDF so I can answer from your course material."
                ),
                "groundedness_note": "Not grounded — LLM and retrieval both unavailable.",
                "pending_followup": None,
            }

        subj_title = message.strip().title()
        return {
            "thought_process": f"LLM unavailable; treating message as a subject declaration: {subj_title}.",
            "intent": "SUBJECT_SPECIFIED",
            "extracted_subject": subj_title,
            "is_explanation": False,
            "quiz_data": None,
            "reply": f"Understood! Let's focus on **{subj_title}**.\n\nPlease upload your study notes using the attachment button below, or ask a question from your course material.",
            "groundedness_note": None,
            "pending_followup": None,
        }


# Singleton instance (kept for drop-in compatibility with existing imports)
decision_agent = DecisionAgent()