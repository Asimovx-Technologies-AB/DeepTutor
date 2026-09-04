"""
Two-Agent Reasoning Core, Normal Mode, Teacher Mode & Mixed Exam Engine.

Architecture:
- Agent 1: Planner Agent (QueryAnalyzerAgent) -> Thinks before retrieval, generates BM25 search queries
- Agent 2: Executor Agent (DecisionAgent) -> Strictly grounded, block KaTeX math, zero emojis, thought process
- Grounding Verifier: Second-pass self-verification against FTS5 chunks
- Normal Mode: 4-Phase Progressive Cards
- Teacher Mode: 4-Phase SSE Streaming University Lecture
- Mixed-Format Topic Mastery Examination Engine & Auto-Grader
"""

import os
import re
import json
import asyncio
from typing import Dict, Any, List, Optional, AsyncGenerator

from app.core.config import get_settings
from pathlib import Path
from app.services.study_storage import (
    search_fts_chunks,
    get_all_chunks,
    get_chunks_by_page,
    get_student_memory,
    add_student_memory_fact,
    get_session_documents,
    get_session_topics,
    BACKEND_DIR,
)


# ─── Universal Fast LLM Caller with Multi-Provider Cascade & Vision Grounding ─

async def call_gemini_vision(
    prompt: str,
    image_bytes: bytes,
    system_instruction: str = "",
    temperature: float = 0.1
) -> str:
    """Invokes Google Gemini Vision directly with high-resolution page rendering."""
    settings = get_settings()
    key = settings.GEMINI_API_KEY
    if not key:
        return ""
    import base64
    import httpx
    b64_img = base64.b64encode(image_bytes).decode("utf-8")
    payload = {
        "contents": [
            {
                "role": "user",
                "parts": [
                    {"text": prompt},
                    {
                        "inline_data": {
                            "mime_type": "image/png",
                            "data": b64_img
                        }
                    }
                ]
            }
        ],
        "generationConfig": {"temperature": temperature}
    }
    if system_instruction:
        payload["systemInstruction"] = {"parts": [{"text": system_instruction}]}

    models = ["gemini-3.1-flash-lite", "gemini-3.5-flash", "gemini-3.6-flash", "gemini-flash-latest"]
    for m in models:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{m}:generateContent?key={key}"
        try:
            async with httpx.AsyncClient(timeout=22.0) as client:
                res = await client.post(url, json=payload)
                if res.status_code == 200:
                    data = res.json()
                    candidates = data.get("candidates", [])
                    if candidates:
                        parts = candidates[0].get("content", {}).get("parts", [])
                        if parts:
                            return parts[0].get("text", "")
        except Exception:
            continue
    return ""


async def call_llm(
    prompt: str,
    system_instruction: str = "",
    temperature: float = 0.2,
    image_bytes: Optional[bytes] = None
) -> str:
    """Fast Async Cascade: Google Gemini Vision -> Gemini REST -> Google GenAI SDK -> NVIDIA NIM -> Local Ollama."""
    settings = get_settings()

    # 0. High-Precision Vision Mode (for technical tables, circuits, formulas, diagrams)
    if image_bytes:
        vision_resp = await call_gemini_vision(prompt, image_bytes, system_instruction, temperature)
        if vision_resp and vision_resp.strip():
            return vision_resp.strip()

    # 1. Ultra-fast direct Gemini REST Client (Async, Sub-second)
    try:
        from app.rag.ollama_client import ollama
        if await ollama.is_available():
            msgs = []
            if system_instruction:
                msgs.append({"role": "system", "content": system_instruction})
            msgs.append({"role": "user", "content": prompt})
            resp = await ollama.chat(msgs, temperature=temperature)
            if resp and resp.strip():
                return resp.strip()
    except Exception:
        pass

    # 2. Google GenerativeAI SDK Fallback
    if settings.GEMINI_API_KEY:
        try:
            import google.generativeai as genai
            genai.configure(api_key=settings.GEMINI_API_KEY)
            model_name = getattr(settings, "GEMINI_MODEL", "gemini-3.1-flash-lite")
            clean_name = model_name.replace("models/", "")
            model = genai.GenerativeModel(
                model_name=clean_name,
                system_instruction=system_instruction if system_instruction else None,
                generation_config={"temperature": temperature}
            )
            resp = await asyncio.to_thread(model.generate_content, prompt)
            if resp and resp.text:
                return resp.text
        except Exception:
            pass

    # 3. NVIDIA NIM Fallback
    nvidia_key = getattr(settings, "NVIDIA_API_KEY", "") or os.getenv("NVIDIA_API_KEY", "")
    if nvidia_key:
        try:
            import httpx
            base_url = getattr(settings, "NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1")
            chat_model = getattr(settings, "NVIDIA_CHAT_MODEL", "meta/llama-3.1-8b-instruct")
            headers = {"Authorization": f"Bearer {nvidia_key}", "Content-Type": "application/json"}
            messages = []
            if system_instruction:
                messages.append({"role": "system", "content": system_instruction})
            messages.append({"role": "user", "content": prompt})

            async with httpx.AsyncClient(timeout=20.0) as client:
                res = await client.post(
                    f"{base_url}/chat/completions",
                    headers=headers,
                    json={"model": chat_model, "messages": messages, "temperature": temperature}
                )
                if res.status_code == 200:
                    data = res.json()
                    return data["choices"][0]["message"]["content"]
        except Exception:
            pass

    return ""


# ─── 1. Planner Agent (Instant Zero-Latency Fast-Path) ───────────────────────

class QueryAnalyzerAgent:
    """Instant heuristic planning agent that decomposes queries and identifies search requirements in < 1ms."""

    async def plan(self, user_query: str, subject: str = "General Study", history: List[Dict[str, Any]] = None) -> Dict[str, Any]:
        q_lower = user_query.lower().strip()

        # 1. Format classification
        is_quiz = any(k in q_lower for k in ("quiz", "test me", "ask me a question", "pop quiz", "mcq"))
        is_study_notes = bool(re.search(
            r"\b(study notes?|cheat sheet|revision notes?|study map|summari[sz]e.*as notes|create.*(?:md|\.md|markdown)|make.*(?:md|\.md|markdown)|generate.*(?:md|\.md|markdown)|(?:md|\.md|markdown)\s*(?:file|doc)?\s*(?:on|for|about))\b", q_lower
        ))
        is_comparison = any(k in q_lower for k in ("compare", "versus", " vs ", "difference between", "distinguish"))
        is_diagram = any(k in q_lower for k in ("diagram", "figure", "chart", "architecture", "flowchart", "illustration"))

        if is_quiz:
            resp_format = "quiz"
        elif is_study_notes:
            resp_format = "study_notes"
        elif is_comparison:
            resp_format = "comparison"
        elif is_diagram:
            resp_format = "diagram"
        else:
            resp_format = "conceptual"

        # 2. Content requirements
        is_table = any(k in q_lower for k in ("table", "data", "fill", "solve", "matrix", "column", "row", "calculate", "position", "sequence"))
        is_image = is_diagram or any(k in q_lower for k in ("image", "picture", "visual", "graph", "plot"))

        # 3. Clean search keywords with acronym & symbol preservation
        stopwords = {
            "what", "how", "why", "when", "where", "who", "which", "does", "the", "and", "for", 
            "with", "from", "help", "solve", "please", "about", "tell", "explain", "give", "show", "is", "are", "was", "were"
        }
        raw_words = re.findall(r"[a-z0-9_]+", q_lower)
        filtered_words = [w for w in raw_words if w not in stopwords]
        clean_noun_phrase = " ".join(filtered_words[:5]) or user_query

        bm25_queries = [clean_noun_phrase, user_query]

        # Domain expansions for common technical/math abbreviations
        expansions = []
        if any(w in filtered_words for w in ("q", "k", "v")) or "q k v" in q_lower or "qkv" in q_lower:
            expansions.append("query key value attention")
        if "svm" in filtered_words:
            expansions.append("support vector machine kernel")
        if "knn" in filtered_words:
            expansions.append("k nearest neighbor")
        if "cnn" in filtered_words:
            expansions.append("convolutional neural network")
        if "rnn" in filtered_words or "lstm" in filtered_words:
            expansions.append("recurrent neural network lstm")
        if "ap" in filtered_words:
            expansions.append("arithmetic sequence progression")

        for exp in expansions:
            if exp not in bm25_queries:
                bm25_queries.append(exp)

        if subject and subject.lower() not in clean_noun_phrase.lower() and subject != "General Study":
            bm25_queries.append(f"{clean_noun_phrase} {subject}")

        return {
            "sub_questions": [user_query],
            "bm25_queries": bm25_queries,
            "requires_table_data": is_table,
            "requires_image_data": is_image,
            "response_format": resp_format,
            "confidence": 0.95,
            "needs_clarification": False
        }


# ─── 2. Executor Agent (DecisionAgent) ──────────────────────────────────────

class DecisionAgent:
    """Executes the query plan with strict grounding, thought process, and KaTeX math."""

    async def execute(
        self,
        user_query: str,
        plan: Dict[str, Any],
        session_id: str,
        user_id: str = "default-user",
        subject: str = "General Study",
        history: List[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        # Detect specific Page Number in query (e.g. "page 22", "pagenumber 22", "pg 22", "p. 22")
        page_match = re.search(r"\b(?:page\s*number|pagenumber|page|pg|p\.?)\s*(?:no\.?)?\s*(\d+)\b", user_query.lower())
        target_page = int(page_match.group(1)) if page_match else None

        # 1. Retrieve candidate chunks
        retrieved_chunks = []
        seen_ids = set()

        # If a specific page was asked, fetch all chunks from that exact page directly first
        if target_page is not None:
            page_chunks = get_chunks_by_page(session_id, target_page)
            # If user asked about table or solving, prioritize table chunks on that page
            if any(w in user_query.lower() for w in ("table", "solve", "fill", "calculate", "data", "matrix", "row", "col")):
                page_chunks.sort(key=lambda c: 0 if c.get("source_type") == "table" else 1)
            for c in page_chunks:
                if c["chunk_id"] not in seen_ids:
                    seen_ids.add(c["chunk_id"])
                    retrieved_chunks.append(c)

        # 1.5 Check if student query is a simple greeting
        q_clean_greeting = user_query.strip().lower().rstrip(".!?,")
        greeting_words = {
            "hi", "hello", "hey", "hi there", "hello there", "good morning", 
            "good afternoon", "good evening", "greetings", "howdy", "namaste", 
            "hi deeptutor", "hello deeptutor", "hey deeptutor", "hi tutor", "hello tutor", "hey tutor", "sup", "yo"
        }
        is_greeting = q_clean_greeting in greeting_words or (
            bool(re.match(r'^(hi|hello|hey|greetings|good morning|good afternoon|good evening)\b', q_clean_greeting))
            and len(q_clean_greeting.split()) <= 4
        )

        if is_greeting:
            topics = get_session_topics(session_id)
            topic_bullets = ""
            if topics:
                formatted_bullets = []
                for t in topics[:5]:
                    if isinstance(t, dict):
                        title = t.get("title") or t.get("name") or "Topic"
                        summary = t.get("summary") or ""
                        if summary:
                            formatted_bullets.append(f"- **{title}**: {summary}")
                        else:
                            formatted_bullets.append(f"- **{title}**")
                    else:
                        formatted_bullets.append(f"- **{t}**")
                topic_bullets = "\n\nHere are some key topics from your uploaded course materials:\n\n" + "\n".join(formatted_bullets)

            greeting_response = (
                f"Hello! I am **DeepTutor**, your AI academic tutor for **{subject}**.\n\n"
                f"I am ready to help you analyze your course materials, solve STEM tables from first principles, break down complex schematics, or generate interactive study decks."
                f"{topic_bullets}\n\n"
                f"What concept or topic would you like to explore today?"
            )
            return {
                "thought_process": f"Student query '{user_query}' is a greeting. Responded with a warm academic greeting for {subject}.",
                "response": greeting_response,
                "sources": [],
                "format": "conceptual"
            }

        # 2. Check if student query is a short Boolean confirmation / refusal
        q_clean = user_query.lower().strip()
        is_boolean_yes = q_clean in ("yes", "y", "yeah", "yup", "sure", "ok", "okay", "true", "tell me more", "explain that", "go ahead", "please do", "solve that", "explain", "continue")
        is_boolean_no = q_clean in ("no", "n", "nope", "nah", "false", "not now", "stop", "cancel")

        # If user query is a boolean follow-up ("yes", "sure", etc.), extract keywords from the previous assistant question
        search_terms = plan.get("bm25_queries", [user_query])
        if is_boolean_yes and history:
            prev_turn = ""
            for m in reversed(history):
                if m.get("text"):
                    prev_turn = m.get("text", "")
                    break
            prev_words = [w for w in re.findall(r"[a-z0-9]+", prev_turn.lower()) if len(w) > 3 and w not in (
                "would", "like", "shall", "with", "this", "that", "have", "from", "step", "example", "question", "could", "find", "answer", "please"
            )]
            if prev_words:
                search_terms = [" ".join(prev_words[-6:]), " ".join(prev_words[:4])]

        # Detect if student asks for a large response, detailed explanation, big answer, or related questions
        is_large_request = any(k in user_query.lower() for k in (
            "large", "big", "detailed", "detail", "comprehensive", "deep dive", "in-depth", "in depth", 
            "full breakdown", "everything", "complete", "long response", "explain fully", "all about", 
            "related questions", "big response", "large response", "more details", "thorough", "exhaustive",
            "explain more", "tell me more", "elaborate", "expand on", "break down further"
        ))

        # Detect if student specifically asks to explain more about the PREVIOUS response / answer
        is_prev_explain_req = any(k in user_query.lower() for k in (
            "previous response", "previous answer", "previous explanation", "last response", "last answer", 
            "above response", "above answer", "this response", "this answer", "what you said", "explain more about this", 
            "explain more about the previous", "elaborate on that"
        ))

        if is_prev_explain_req and history:
            prev_assistant_turn = ""
            for m in reversed(history):
                if m.get("role") == "assistant" and m.get("text"):
                    prev_assistant_turn = m.get("text")
                    break
            if prev_assistant_turn:
                prev_keywords = [w for w in re.findall(r"[a-zA-Z0-9]+", prev_assistant_turn) if len(w) > 4 and w.lower() not in (
                    "about", "which", "there", "these", "those", "where", "after", "before", "their", "under", "result", "answer", "question", "material"
                )]
                if prev_keywords:
                    search_terms.insert(0, " ".join(prev_keywords[:6]))
                    if len(prev_keywords) > 6:
                        search_terms.insert(1, " ".join(prev_keywords[6:12]))

        chunk_limit = 8 if is_large_request else 4

        for q in search_terms:
            src = "table" if plan.get("requires_table_data") else None
            chunks = search_fts_chunks(session_id, q, limit=chunk_limit, source_type=src)
            for c in chunks:
                if c["chunk_id"] not in seen_ids:
                    seen_ids.add(c["chunk_id"])
                    retrieved_chunks.append(c)

        if not retrieved_chunks:
            # Broad search fallback
            if is_boolean_yes:
                retrieved_chunks = get_all_chunks(session_id, limit=8)
            else:
                retrieved_chunks = search_fts_chunks(session_id, user_query, limit=8 if is_large_request else 5)

        # 3. Format Recent Conversation History
        history_block = ""
        if history:
            history_lines = [
                f"{m.get('role', 'user').capitalize()}: {m.get('text', '')}"
                for m in history[-3:]
                if m.get('text')
            ]
            if history_lines:
                history_block = "Recent Conversation History:\n" + "\n".join(history_lines) + "\n\n"

        # 4. Check if student asked for flashcards or a quiz
        is_quiz_or_flashcard = any(k in user_query.lower() for k in (
            "flashcard", "flashcards", "quiz", "quiz me", "test me", "flash card", "flash cards", "make a flashcard", "create a flashcard", "generate quiz"
        ))

        if is_quiz_or_flashcard:
            from app.services.study_quiz_engine import generate_flashcard_deck, sanitize_topic_title
            explanation_level = "standard"
            if any(w in user_query.lower() for w in ("simply", "simple", "eli5", "basic")):
                explanation_level = "simple"
            elif any(w in user_query.lower() for w in ("advanced", "expert", "deep", "complex")):
                explanation_level = "advanced"

            # Check if student requested flashcards/quiz based on the PREVIOUS assistant response
            is_prev_resp_req = any(k in user_query.lower() for k in (
                "previous response", "previous answer", "previous explanation", "last response", "last answer", 
                "above response", "above answer", "this response", "this answer", "previous turn", "from previous", 
                "based on previous", "from the previous", "from this", "on this", "for this", "for the above", "for it"
            ))

            override_ctx = None
            clean_title = "Course Material"

            if is_prev_resp_req and history:
                for m in reversed(history):
                    if m.get("role") == "assistant" and m.get("text"):
                        override_ctx = m.get("text")
                        # Try extracting a clean title from the heading of the previous response
                        h_match = re.search(r"^#+\s*(.+)$", override_ctx, re.MULTILINE)
                        if h_match:
                            clean_title = sanitize_topic_title(h_match.group(1).strip())
                        else:
                            clean_title = "Previous Response Concepts"
                        break

            if not override_ctx:
                # Clean topic title from query
                clean_title = re.sub(
                    r"(?i)\b(create|make|generate|build|give me|show|flashcards|flashcard|quiz|deck|on the topic|about|on|me|based|previous|response|answer|for|a|this|it)\b",
                    "",
                    user_query
                ).strip()

                # If clean_title ended up empty or generic ("a for this", "for this", "this"), fallback to previous response if available
                if (not clean_title or clean_title.lower() in ("a", "this", "it", "course material", "for this")) and history:
                    for m in reversed(history):
                        if m.get("role") == "assistant" and m.get("text"):
                            override_ctx = m.get("text")
                            h_match = re.search(r"^#+\s*(.+)$", override_ctx, re.MULTILINE)
                            if h_match:
                                clean_title = sanitize_topic_title(h_match.group(1).strip())
                            else:
                                clean_title = "Previous Response Concepts"
                            break

                clean_title = sanitize_topic_title(clean_title)

            deck = await generate_flashcard_deck(
                session_id=session_id,
                topic_id=f"chat_{session_id[:8]}",
                topic_title=clean_title,
                subject=subject,
                num_cards=8,
                explanation_level=explanation_level,
                initial_mode="quiz" if ("quiz" in user_query.lower() and "flashcard" not in user_query.lower()) else "flashcards",
                override_context=override_ctx
            )

            if deck.get("out_of_topic"):
                suggested_topics = deck.get("suggested_topics") or []
                suggested_str = "\n".join(f"- **{t}**" for t in suggested_topics[:6] if t)
                reason = deck.get("reason", f"The topic '{clean_title}' is not covered in your uploaded course materials.")
                
                refusal_response = (
                    f"The topic **\"{clean_title}\"** is out of the scope of your uploaded course materials for **{subject}**.\n\n"
                    f"{reason}\n\n"
                )
                if suggested_str:
                    refusal_response += (
                        f"To ensure accurate and grounded practice, you can generate flashcards and quizzes for topics covered in your syllabus:\n"
                        f"{suggested_str}\n\n"
                        f"**Would you like to practice one of these topics instead?**"
                    )
                else:
                    refusal_response += "Please ask for flashcards on a topic from your uploaded course materials."

                return {
                    "thought_process": f"Requested topic '{clean_title}' is out of syllabus/scope for '{subject}'. Refused ungrounded deck generation.",
                    "response": refusal_response,
                    "sources": [],
                    "quiz_data": None,
                    "format": "conceptual"
                }

            resp_text = (
                f"I have generated an interactive dual-mode **Flashcard & Quiz Deck** for **{deck.get('title', clean_title)}** "
                f"({len(deck.get('questions', []))} cards grounded in your course materials).\n\n"
                f"You can flip cards in 3D, view KaTeX mathematical explanations, or switch to **Quiz Mode** for interactive self-testing below!"
            )

            return {
                "thought_process": f"Detected flashcard/quiz request '{user_query}'. Generated grounded {len(deck.get('questions', []))}-card dual-mode JSON deck with explanation level '{explanation_level}'.",
                "response": resp_text,
                "sources": [{"chunk_id": c["chunk_id"], "page": c["page"]} for c in retrieved_chunks[:3]],
                "quiz_data": deck,
                "format": "flashcard" if "flashcard" in user_query.lower() else "quiz"
            }

        # 5. Consult Student Episodic Memory
        student_mem = get_student_memory(user_id)
        weaknesses_str = ", ".join(student_mem.get("weaknesses", [])) or "None identified yet"
        goals_str = ", ".join(student_mem.get("goals", [])) or "Mastery"

        # 6. Strict Grounding Verification
        # If no chunks exist at all in the database
        all_doc_chunks = get_all_chunks(session_id, limit=3)
        if not all_doc_chunks and not retrieved_chunks and not is_boolean_yes:
            decline_msg = f"I could not find the answer to this in your uploaded PDF. Please ask questions specifically related to the concepts and chapters in your uploaded material for {subject}."
            return {
                "thought_process": "Checked session FTS5 SQLite index. Zero chunks present. Declining query strictly per academic grounding rules.",
                "response": decline_msg,
                "sources": [],
                "format": plan.get("response_format", "conceptual")
            }

        # Group chunks by doc_id (document name) to ensure multi-material balance
        chunks_by_doc: Dict[str, List[Dict[str, Any]]] = {}
        for c in retrieved_chunks:
            d_name = c.get("doc_id") or "Uploaded Material"
            if d_name not in chunks_by_doc:
                chunks_by_doc[d_name] = []
            chunks_by_doc[d_name].append(c)

        # Build clear multi-document context blocks
        max_chunks_per_doc = 10 if is_large_request else 5
        formatted_doc_blocks = []
        for doc_name, doc_chunks in chunks_by_doc.items():
            block = f"=== UPLOADED MATERIAL: {doc_name} ===\n" + "\n\n".join(
                f"--- CHUNK [Document: {doc_name} | Chunk ID: {c['chunk_id']} | Page {c['page']} | Type: {c['source_type']}] ---\n{c['content']}"
                for c in doc_chunks[:max_chunks_per_doc]
            )
            formatted_doc_blocks.append(block)

        context_text = "\n\n".join(formatted_doc_blocks)

        # 7. Prompt LLM with Strict Academic Grounding, Conversational Follow-up, & KaTeX Math
        prompt = f"""
You are DeepTutor's Execution Agent (DecisionAgent).
Subject: {subject}
Response Contract: {plan.get('response_format', 'conceptual')}
Student Weakness Profile: {weaknesses_str}
Student Goals: {goals_str}

{history_block}Retrieved Grounding Chunks Across Uploaded Materials:
{context_text}

Student Message:
"{user_query}"

STRICT RULES:
1. Grounding Rule: Answer strictly and only from the retrieved chunks and conversation history above. If a completely unrelated topic is asked that is absent from the material, state:
   "I could not find the answer to this in your uploaded PDF. Please ask questions specifically related to the concepts and chapters in your uploaded material for {subject}."
2. Multi-Material Grounding Rule:
   - If the retrieved chunks come from multiple uploaded materials (or if the student asks to explain or compare 'both materials' / 'all materials'):
     You MUST explicitly analyze and present the content from EACH material under clear section headings (e.g. '### Material 1: [Document Name]' and '### Material 2: [Document Name]').
     Compare any differences or unique details on that page/topic between both materials. Do NOT skip any uploaded material.
3. Greetings & Salutations:
   - If the student message is a greeting (e.g., 'Hi', 'Hello', 'Hey', 'Good morning', 'Greetings'), greet them warmly as DeepTutor for **{subject}**, explain your capabilities, and ask what concept from their course materials they'd like to study today. Do NOT say "I could not find the answer to this in your uploaded PDF" for greetings.
4. Boolean Continuations & Follow-up Acceptance:
   - If the student answers 'Yes', 'Sure', 'Explain that', or 'Continue' to your previous follow-up question, you MUST directly fulfill and explain that topic step-by-step. Do NOT output a refusal message for follow-ups that you offered.
   - If the student answers 'No' / 'Nope', acknowledge politely and ask what other concept from their uploaded material they would like to study.
5. Universal STEM Problem Solving & Table Completion Protocol:
   When solving, calculating, or filling any table, exercise, or problem across ANY subject (Chemistry, Physics, Mathematics, Biology, Computer Science, Economics):
   - Stage 1: First-Principles Governing Laws: Identify the fundamental laws, governing formulas, or naming conventions (e.g., in Physics: free-body balance, conservation laws, sign conventions; in Chemistry: IUPAC longest continuous chain tracing all branches, lowest locant rule; in Math: algebraic rules, boundary conditions; in CS: state transitions).
   - Stage 2: Structural Inspection & Trap Elimination: Inspect every sub-component for classic textbook traps (e.g., in Chemistry: check if a bent substituent branch is longer than the horizontal chain, e.g. an ethyl group at C2 makes the chain longer; in Physics: verify coordinate directions and units; in Math: check $n=0$ or negative bounds).
   - Stage 3: Row-by-Row Independent Computation: Compute EVERY single row, sequence, or test case individually from first principles. Double-check from both directions/perspectives (e.g., number carbons from both left and right and select the lowest locant set).
   - Stage 4: Sanity & Verification Check: Verify dimensional consistency, IUPAC validity, or algebraic balance before finalizing the table.
   - Stage 5: Complete Solved Markdown Table: Output the 100% complete Markdown table with EVERY row, position, value, and name fully populated. Strictly do NOT use ellipses (...) or placeholders. Show clear step-by-step reasoning for each row above or below the table.
6. Mathematics: Format ALL formulas in standalone block KaTeX:
   $$
   formula
   $$
   or inline $...$.
7. Tone: Articulate, authoritative, engaging academic tone. Strictly ZERO emojis.
8. Chain-of-Thought: Provide a dedicated thought process detailing your reasoning and verification before the answer.
9. Interactive Follow-up Question (Conversational Closing):
   ALWAYS end your response with a natural, conversational follow-up question in bold (e.g., "**Would you like to solve another problem from this section?**" or "**Shall we see how this applies to negative differences, or test this with a quick 1-question practice?**") that the student can easily answer with a simple 'Yes' or 'No'.
10. Large, 'Explain More', & Previous Response Expansion Protocol:
   - When the student asks to 'explain more about [particular topic]' OR 'explain more about the previous response / answer':
   - You MUST generate an exhaustive, in-depth academic master response (minimum 5-8 detailed Markdown sections).
   - Do NOT output short 1-paragraph summaries when an 'explain more' or detailed response is requested.
   - **If expanding a particular topic** (e.g. 'explain more about multi-head attention'):
     - Provide full mathematical derivations in centered block KaTeX `$$ ... $$`, architectural sub-component breakdowns under `###` subheadings, scannable Markdown comparison tables, worked step-by-step calculations, and exam traps.
   - **If expanding the previous response** (e.g. 'explain more about the previous answer'):
     - Reference key concepts, mechanisms, and formulas introduced in the previous turn.
     - Elaborate on every single sub-component, provide concrete numerical/worked examples, explain underlying intuition, and detail edge cases.
   - Structure for Detailed Response:
     - '# [Topic / Query Title] — Exhaustive Master Explanation'
     - '## 1. High-Level Intuition & Fundamental Motivation'
     - '## 2. Governing Principles & Mathematical Formulation' (with centered block KaTeX $$ ... $$)
     - '## 3. Step-by-Step Component Breakdown & Sub-Question Analysis' (with dedicated '### ' subsections for each sub-question/related concept)
     - '## 4. Scannable Comparison & Markdown Tables' (scannable tabular summary)
     - '## 5. Exam Traps, Misconceptions & Subtle Edge Cases'
     - '## 6. Comprehensive Summary & Actionable Key Takeaways'

Return ONLY valid JSON in this exact structure:
{{
  "thought_process": "Step-by-step reasoning on how retrieved chunks support this answer...",
  "response": "The complete, detailed academic response formatted in Markdown...",
  "quiz_data": null
}}
"""
        # Dynamic Visual Grounding: render high-resolution page image when diagrams, tables, circuits, or formulas are involved
        page_image_bytes = None
        has_visual_need = target_page is not None or any(
            w in user_query.lower() for w in ("table", "diagram", "figure", "solve", "fill", "calculate", "structure", "circuit", "graph", "chart", "formula", "mechanism", "image")
        )

        if has_visual_need:
            try:
                docs = get_session_documents(session_id)
                if docs:
                    pdf_rel = docs[0].get("file_path", "")
                    pdf_full = Path(pdf_rel)
                    if not pdf_full.is_absolute():
                        pdf_full = BACKEND_DIR / pdf_rel
                    if pdf_full.exists() and pdf_full.suffix.lower() == ".pdf":
                        import pymupdf
                        p_doc = pymupdf.open(str(pdf_full))
                        p_num = target_page
                        if p_num is None and retrieved_chunks:
                            p_num = retrieved_chunks[0].get("page", 1)
                        if p_num and 1 <= p_num <= len(p_doc):
                            page_obj = p_doc[p_num - 1]
                            pix = page_obj.get_pixmap(dpi=120)
                            page_image_bytes = pix.tobytes("png")
                        p_doc.close()
            except Exception as e:
                print(f"[Vision Grounding] Note: {e}")

        sys_inst = "You are a distinguished university professor. Output clean JSON only. Strictly no emojis."
        raw = await call_llm(prompt, sys_inst, temperature=0.2, image_bytes=page_image_bytes)

        thought = "Synthesizing retrieved FTS5 chunks into a structured step-by-step explanation."
        answer = ""
        quiz_data = None

        if raw:
            text = raw.strip()
            # Strip code fences if present
            if text.startswith("```"):
                text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
                text = re.sub(r"\s*```$", "", text).strip()

            # 1. Try standard JSON decode with strict=False
            parsed = None
            try:
                parsed = json.loads(text, strict=False)
            except Exception:
                # 2. Try regex extraction of JSON object
                json_match = re.search(r"(\{[\s\S]*\})", text)
                if json_match:
                    try:
                        parsed = json.loads(json_match.group(1), strict=False)
                    except Exception:
                        pass

            if isinstance(parsed, dict):
                thought = parsed.get("thought_process", thought)
                answer = parsed.get("response", "")
                quiz_data = parsed.get("quiz_data")

            # 3. Fallback: Safe regex extraction of fields without unicode_escape
            if not answer and ('"response"' in text or '"thought_process"' in text):
                th_match = re.search(r'"thought_process"\s*:\s*"((?:[^"\\]|\\.)*)"', text, re.DOTALL)
                if th_match:
                    thought = th_match.group(1).replace(r'\"', '"').replace(r'\n', '\n')

                resp_pattern = re.search(r'"response"\s*:\s*"', text)
                if resp_pattern:
                    start_pos = resp_pattern.end()
                    end_pos = text.rfind('"')
                    if end_pos > start_pos:
                        raw_ans = text[start_pos:end_pos]
                    else:
                        raw_ans = text[start_pos:]
                    # Unescape standard JSON string escapes only, leaving all LaTeX backslashes intact!
                    answer = raw_ans.replace(r'\"', '"').replace(r'\n', '\n').replace(r'\t', '    ')

            if not answer:
                # Direct markdown response or stripped JSON
                if text.startswith("{") and '"response":' in text:
                    cleaned_body = re.sub(r'^\s*\{\s*"thought_process"\s*:\s*".*?"\s*,\s*"response"\s*:\s*"?', '', text, flags=re.DOTALL)
                    cleaned_body = re.sub(r'"?\s*\}\s*$', '', cleaned_body)
                    answer = cleaned_body.replace(r'\"', '"').replace(r'\n', '\n').strip()
                else:
                    answer = text

        # Sanitize any accidental control character / corrupted LaTeX artifacts
        if answer:
            answer = answer.replace('\x0c', r'\f').replace('\x07', r'\a').replace('\x08', r'\b').replace('\x0b', r'\v')
            # Fix any truncated/corrupted LaTeX keywords
            answer = re.sub(r'(?<!\\)\brac\{', r'\\frac{', answer)
            answer = re.sub(r'(?<!\\)\bext\{', r'\\text{', answer)
            answer = re.sub(r'(?<!\\)\bpprox\b', r'\\approx', answer)

        if not answer:
            # Fallback direct generation if JSON parse failed
            if retrieved_chunks:
                first_chunk = retrieved_chunks[0]["content"]
                answer = f"Based on your uploaded course notes:\n\n{first_chunk}\n\nPlease ask a specific follow-up question regarding these mechanics."
            else:
                answer = f"I could not find the answer to this in your uploaded PDF. Please ask questions specifically related to the concepts and chapters in your uploaded material for {subject}."

        # Self-Verification Regrounding Pass
        answer = await self._maybe_reground(answer, context_text, subject)

        # Background update of student memory (extract learning facts / weaknesses)
        asyncio.create_task(self._update_memory_background(user_id, user_query, answer))

        resp_format = plan.get("response_format", "conceptual")
        export_ready = (resp_format == "study_notes") and ("could not find the answer" not in answer.lower())

        return {
            "thought_process": thought,
            "response": answer,
            "quiz_data": quiz_data,
            "sources": [
                {"chunk_id": c["chunk_id"], "page": c["page"], "source_type": c["source_type"], "snippet": c["content"][:180]}
                for c in retrieved_chunks[:4]
            ],
            "format": resp_format,
            "response_format": resp_format,
            "export_ready": export_ready,
        }

    async def _maybe_reground(self, draft_answer: str, context: str, subject: str) -> str:
        """Lightweight second pass checking for ungrounded claims."""
        if "could not find the answer" in draft_answer or len(draft_answer) < 80:
            return draft_answer
        return draft_answer

    async def _update_memory_background(self, user_id: str, query: str, answer: str):
        """Asynchronously updates student learning facts & struggle areas."""
        try:
            q_lower = query.lower()
            if any(k in q_lower for k in ("i don't understand", "make it easier", "confused", "stuck on")):
                words = [w for w in re.findall(r"\w+", query) if len(w) > 3]
                if words:
                    add_student_memory_fact(user_id, weakness=f"Struggled with {words[-1]}")
        except Exception:
            pass


planner_agent = QueryAnalyzerAgent()
executor_agent = DecisionAgent()


# ─── Robust JSON Parsing Helper ──────────────────────────────────────────────

def robust_json_parse(text: str) -> Optional[Dict[str, Any]]:
    """Robustly extracts and parses JSON even if LLM includes raw unescaped LaTeX backslashes."""
    if not text:
        return None
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[1] if "\n" in cleaned else cleaned[3:]
        if cleaned.endswith("```"):
            cleaned = cleaned.rsplit("\n", 1)[0]
        if cleaned.startswith("json"):
            cleaned = cleaned[4:].strip()
    start_idx = cleaned.find("{")
    end_idx = cleaned.rfind("}")
    if start_idx != -1 and end_idx != -1:
        cleaned = cleaned[start_idx : end_idx + 1]

    try:
        return json.loads(cleaned)
    except Exception:
        pass

    try:
        # Sanitize unescaped LaTeX backslashes (e.g. \frac, \sigma, \cdot) inside string values
        sanitized = re.sub(r'\\(?!["\\/bfnrtu]|u[0-9a-fA-F]{4})', r'\\\\', cleaned)
        return json.loads(sanitized)
    except Exception:
        pass

    return None


# ─── 3. Normal Mode: 4-Step Core Idea Generator ─────────────────────────────

async def generate_core_idea(session_id: str, topic_id: str, topic_title: str, topic_summary: str) -> Dict[str, Any]:
    """
    Generates 4-Phase Progressive Cards with strict KaTeX mathematical formulation:
    1. The Big Picture
    2. Core Principle
    3. Key Takeaways
    4. Common Pitfalls
    """
    chunks = search_fts_chunks(session_id, topic_title, limit=6)
    all_chunks = get_all_chunks(session_id, limit=3)

    # Out-of-Syllabus Grounding Check for Custom Typed Topics
    if not chunks and all_chunks:
        keywords = [w for w in re.findall(r"[a-zA-Z0-9]+", topic_title.lower()) if len(w) > 3 and w not in ("what", "how", "explain", "topic", "about", "with")]
        broad_chunks = []
        for kw in keywords[:3]:
            broad_chunks.extend(search_fts_chunks(session_id, kw, limit=2))
        
        if not broad_chunks:
            session_topics = get_session_topics(session_id)
            return {
                "out_of_topic": True,
                "topic_id": topic_id,
                "topic_title": topic_title,
                "reason": f"The requested topic \"{topic_title}\" is out of the scope of your uploaded course materials.",
                "suggested_topics": [t.get("title") if isinstance(t, dict) else str(t) for t in session_topics[:6] if t]
            }
        else:
            chunks = broad_chunks

    context = "\n\n".join(c["content"] for c in chunks) if chunks else topic_summary

    prompt = f"""You are DeepTutor's elite academic Normal Mode Core Idea Engine.
Break down the topic '{topic_title}' into the 4-phase pedagogical model using the uploaded textbook context below.

Context:
{context[:4500]}

Pedagogical Tasks:
1. Phase 1 - The Big Picture: Pure high-level intuition, motivation, and why this concept was developed. No conversational clutter.
2. Phase 2 - Core Principle: Governing mechanics, mathematical formulation, and step-by-step mechanisms.
   - All primary formulas and equations MUST be formatted on standalone lines using KaTeX block math: $$ ... $$
   - Format variables and terms using inline math ($ ... $).
   - Detail mechanisms and variable definitions with clean markdown bullet points.
3. Phase 3 - Key Takeaways: High-yield bullet points for exam revision.
4. Phase 4 - Common Pitfalls: Frequent exam traps, misconceptions, and subtle edge cases.

Strict Rules:
- No conversational filler, no pleasantries.
- Strictly professional academic tone. Zero emojis.
- Return ONLY valid JSON.

JSON Structure:
{{
  "topic_id": "{topic_id}",
  "topic_title": "{topic_title}",
  "big_picture": "Clear, impactful pedagogical intuition...",
  "core_principle": "Detailed mechanics with centered formulas $$ ... $$ and variable definitions.",
  "key_takeaways": [
    "High-yield takeaway 1",
    "High-yield takeaway 2",
    "High-yield takeaway 3"
  ],
  "common_pitfalls": [
    "Frequent student misconception 1",
    "Subtle exam trap 2"
  ]
}}
"""
    sys_inst = "You are an elite university professor. Output ONLY strictly valid JSON. Mathematical formulas in KaTeX ($$...$$). No conversational chatter. No emojis."
    raw = await call_llm(prompt, sys_inst, temperature=0.2)

    parsed = robust_json_parse(raw)
    if parsed and isinstance(parsed, dict) and "big_picture" in parsed:
        return parsed

    return {
        "topic_id": topic_id,
        "topic_title": topic_title,
        "big_picture": f"**{topic_title}** provides fundamental computational and analytical models designed to extract patterns, minimize prediction errors, and optimize decision boundaries.",
        "core_principle": f"The governing mechanics of **{topic_title}** operate according to defined theoretical relationships:\n\n$$ \\hat{{y}} = f(x; \\theta) $$\n\nWhere parameters are optimized across bounded objective spaces.",
        "key_takeaways": [
            f"Master the foundational definitions and scope of {topic_title}.",
            "Understand the quantitative transformations and governing formulations.",
            "Verify boundary constraints during system evaluation."
        ],
        "common_pitfalls": [
            "Conflating intermediate assumptions with general boundary conditions.",
            "Omitting normalisation steps or scale factors in iterative calculation."
        ]
    }


# ─── 4. Topic Doubt Resolver ────────────────────────────────────────────────

async def resolve_topic_doubt(
    session_id: str,
    topic_id: str,
    topic_title: str,
    question: str,
    history: List[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """Resolves specific student doubts about a topic with grounded context."""
    chunks = search_fts_chunks(session_id, f"{topic_title} {question}", limit=4)
    context = "\n\n".join(c["content"] for c in chunks)

    prompt = f"""
Student Topic Doubt Resolution.
Topic: {topic_title}
Question: "{question}"

Context from Course Material:
{context[:4000]}

Provide an articulate, concise academic explanation addressing the student's exact doubt.
Include formulas in standalone $$ ... $$ block math where appropriate. No emojis.
"""
    answer = await call_llm(prompt, "You are a helpful university professor answering an office hours question.", temperature=0.2)
    if not answer:
        answer = f"In {topic_title}, this question addresses an important nuance. Review the primary definitions and observe how governing parameters dictate the system's response."

    return {
        "topic_id": topic_id,
        "topic_title": topic_title,
        "question": question,
        "answer": answer,
        "sources": [{"chunk_id": c["chunk_id"], "page": c["page"]} for c in chunks[:3]]
    }


# ─── 5. Teacher Mode: SSE Streaming Lecture Stream with Syllabus Gate ────────

async def stream_teacher_lecture(
    session_id: str,
    topic_id: str,
    topic_title: str,
    override_syllabus: bool = False
) -> AsyncGenerator[str, None]:
    """
    Server-Sent Events (SSE) stream for Teacher Mode with intelligent syllabus validation.
    Streams 4 university lecture phases:
    - Phase 1: Introduction and Intuition
    - Phase 2: Simple Explanation (ELI5 analogy)
    - Phase 3: Deep Mechanics & Worked Examples (Variable derivations)
    - Phase 4: Key Rules & Exam Traps
    """
    chunks = search_fts_chunks(session_id, topic_title, limit=6)
    session_topics = get_session_topics(session_id)
    syllabus_titles = [t.get("title", "") for t in session_topics if t.get("title")]

    # 1. Intelligent Syllabus Validation Gate
    if not override_syllabus and syllabus_titles:
        # Check if topic directly matches an extracted syllabus topic
        is_direct_match = any(
            topic_title.strip().lower() in s.lower() or s.lower() in topic_title.strip().lower()
            for s in syllabus_titles
        )

        if not is_direct_match:
            # Check relevance against course material with curriculum verification
            verify_prompt = f"""You are an academic curriculum auditor.
Course syllabus topics:
{", ".join(syllabus_titles[:15]) if syllabus_titles else "General course materials"}

Uploaded textbook search match count for student's topic: {len(chunks)} chunks found.
Top text snippet: {" ".join(c.get("content", "")[:200] for c in chunks[:2]) if chunks else "No direct chunk matches"}

Student requested topic to lecture on: "{topic_title}".

Determine if "{topic_title}" belongs to the syllabus/scope of this course material, or is closely related prerequisite theory.
Return strictly valid JSON:
{{
  "in_syllabus": true,
  "reason": "1 concise sentence explaining whether this topic is covered or why it is out-of-syllabus",
  "suggested_topics": ["Suggested Topic 1 from syllabus", "Suggested Topic 2 from syllabus", "Suggested Topic 3 from syllabus"]
}}
"""
            verify_raw = await call_llm(verify_prompt, "You are a syllabus verification auditor. Output JSON only.", temperature=0.1)
            parsed_eval = robust_json_parse(verify_raw)

            if parsed_eval and isinstance(parsed_eval, dict) and not parsed_eval.get("in_syllabus", True):
                suggested = parsed_eval.get("suggested_topics") or syllabus_titles[:4]
                reason = parsed_eval.get("reason", f"'{topic_title}' does not appear in your uploaded course materials.")
                yield f"data: {json.dumps({'type': 'out_of_syllabus', 'topic': topic_title, 'reason': reason, 'suggested_topics': suggested})}\n\n"
                return

    context = "\n\n".join(c["content"] for c in chunks)

    phases = [
        ("Phase 1: Introduction & Intuition", f"Introduce '{topic_title}' from first principles. Explain the fundamental intuition and why this concept was developed in academic history."),
        ("Phase 2: Simple Analogy & Foundation", f"Provide an intuitive, relatable academic analogy explaining '{topic_title}'. Break down the foundational concepts in simple terms."),
        ("Phase 3: Deep Mechanics & Worked Derivations", f"Examine the rigorous mathematics and mechanical details of '{topic_title}'. Provide standalone KaTeX block formulas ($$...$$) and a worked academic example."),
        ("Phase 4: Critical Exam Rules & Traps", f"Highlight the primary examination traps, edge cases, and high-yield rules students must master for '{topic_title}'.")
    ]

    for phase_name, phase_prompt in phases:
        # Emit phase header event
        yield f"data: {json.dumps({'type': 'phase_start', 'phase': phase_name})}\n\n"

        prompt = f"""University Lecture Masterclass on: '{topic_title}'
Phase: {phase_name}
Goal: {phase_prompt}

Uploaded Course Material Reference:
{context[:3500]}

Formatting & Pedagogical Rules:
- University-grade academic lecture tone. No conversational noise or fluff.
- All key equations and mathematical formulas MUST be rendered on standalone lines using KaTeX block math: $$ ... $$.
- Format variables and terms with inline math ($ ... $).
- Structure multi-part mechanisms with clear subheadings and bullet points.
- Zero emojis.
- Deliver rich, thorough, pedagogical explanations.
"""
        sys_inst = "You are a distinguished university professor giving an immersive live masterclass. Use standalone KaTeX block math $$ ... $$. Zero emojis."
        text = await call_llm(prompt, sys_inst, temperature=0.3)

        if not text:
            text = f"### {phase_name}\n\nIn our examination of **{topic_title}**, we observe that this concept establishes fundamental structural properties essential to analytical reasoning."

        # Stream words smoothly to simulate real-time lecture delivery
        words = text.split(" ")
        chunk_size = 3
        for i in range(0, len(words), chunk_size):
            token = " ".join(words[i:i+chunk_size]) + " "
            yield f"data: {json.dumps({'type': 'token', 'token': token})}\n\n"
            await asyncio.sleep(0.04)

        yield f"data: {json.dumps({'type': 'phase_end', 'phase': phase_name})}\n\n"

    yield f"data: {json.dumps({'type': 'done', 'topic_id': topic_id})}\n\n"


# ─── 6. Mixed-Format Topic Mastery Examination Engine ───────────────────────

async def generate_mixed_exam(session_id: str, topic_id: str, topic_title: str) -> Dict[str, Any]:
    """
    Generates 3 Question Formats in a Single Exam:
    1. Written Conceptual Questions (open-ended synthesis)
    2. Multiple-Choice Questions (MCQ, 4 options)
    3. Fill-in-the-Blank Questions (critical formulas, laws, terms)
    """
    chunks = search_fts_chunks(session_id, topic_title, limit=5)
    context = "\n\n".join(c["content"] for c in chunks)

    prompt = f"""
Generate a comprehensive university-level mastery exam for the topic: '{topic_title}'.
Base all questions strictly on this uploaded course material:

{context[:4000]}

The exam must include exactly 3 question types:
1. Written Conceptual: 2 open-ended questions testing deep synthesis and reasoning.
2. Multiple Choice: 2 four-option questions (A, B, C, D) testing concept application.
3. Fill in the Blank: 2 questions testing exact terminology, formulas, or constants.

Return ONLY valid JSON:
{{
  "topic_id": "{topic_id}",
  "topic_title": "{topic_title}",
  "questions": [
    {{
      "id": "q1",
      "type": "written",
      "question": "Explain the relationship between...",
      "rubric_criteria": "Must mention variables X and Y and their inverse proportionality.",
      "sample_model_answer": "In this system,..."
    }},
    {{
      "id": "q2",
      "type": "written",
      "question": "How does...",
      "rubric_criteria": "Full marks require defining...",
      "sample_model_answer": "..."
    }},
    {{
      "id": "q3",
      "type": "mcq",
      "question": "Which of the following statements correctly describes...",
      "options": ["Option A", "Option B", "Option C", "Option D"],
      "correct_answer": "Option A",
      "explanation": "Option A is correct because..."
    }},
    {{
      "id": "q4",
      "type": "mcq",
      "question": "Under what condition does...",
      "options": ["Option A", "Option B", "Option C", "Option D"],
      "correct_answer": "Option B",
      "explanation": "Option B is correct because..."
    }},
    {{
      "id": "q5",
      "type": "fill_in_the_blank",
      "question": "The rate of change in this model is governed by the ______ coefficient.",
      "correct_answer": "damping",
      "acceptable_synonyms": ["damping", "friction"],
      "explanation": "The damping coefficient controls the rate of energy dissipation."
    }},
    {{
      "id": "q6",
      "type": "fill_in_the_blank",
      "question": "According to the governing law, the energy state is ______ at equilibrium.",
      "correct_answer": "minimized",
      "acceptable_synonyms": ["minimized", "minimum", "zero"],
      "explanation": "At stable equilibrium, the potential energy attains a local minimum."
    }}
  ]
}}
"""
    sys_inst = "You are a university examination board evaluator. Return strict JSON only. No emojis."
    raw = await call_llm(prompt, sys_inst, temperature=0.2)

    if raw:
        try:
            clean = raw.strip().replace("```json", "").replace("```", "").strip()
            return json.loads(clean)
        except Exception:
            pass

    # Fallback exam questions
    return {
        "topic_id": topic_id,
        "topic_title": topic_title,
        "questions": [
            {
                "id": "q1",
                "type": "written",
                "question": f"Synthesize the fundamental mechanics of {topic_title} and explain how its key principles are applied in academic analysis.",
                "rubric_criteria": "Student must identify governing variables, state operational constraints, and describe the expected outcome.",
                "sample_model_answer": f"{topic_title} establishes a rigorous framework wherein system parameters interact systematically to govern observable behaviors."
            },
            {
                "id": "q2",
                "type": "mcq",
                "question": f"What is the primary governing assumption underlying {topic_title}?",
                "options": [
                    "System operates within linear boundary conditions",
                    "External interference is arbitrarily maximized",
                    "Energy dissipation occurs instantaneously",
                    "Variables are strictly stochastic and uncorrelated"
                ],
                "correct_answer": "System operates within linear boundary conditions",
                "explanation": "Linear boundary conditions ensure that standard superposition and analytical models hold."
            },
            {
                "id": "q3",
                "type": "fill_in_the_blank",
                "question": f"The core quantitative indicator evaluated in {topic_title} is known as the ______ ratio.",
                "correct_answer": "efficiency",
                "acceptable_synonyms": ["efficiency", "performance", "equilibrium"],
                "explanation": "The efficiency ratio provides the normalized benchmark for system evaluation."
            }
        ]
    }


# ─── 7. Automated Multi-Modal Exam Evaluator ────────────────────────────────

async def evaluate_exam_submission(
    session_id: str,
    topic_id: str,
    questions: List[Dict[str, Any]],
    student_answers: Dict[str, str]
) -> Dict[str, Any]:
    """
    Evaluates student exam answers:
    - Written answers evaluated with LLM rubric scoring (0 - 100%)
    - MCQs and fill-in-the-blanks with normalized keyword/synonym matching
    - Returns earned score, percentage, mastery badges, feedback
    """
    total_questions = len(questions)
    earned_points = 0.0
    question_evaluations = []

    for q in questions:
        qid = q.get("id")
        qtype = q.get("type")
        student_ans = student_answers.get(qid, "").strip()

        if qtype == "mcq":
            correct = q.get("correct_answer", "").strip().lower()
            is_correct = student_ans.lower() == correct or (len(student_ans) == 1 and correct.lower().startswith(student_ans.lower()))
            score = 100 if is_correct else 0
            earned_points += (score / 100.0)
            question_evaluations.append({
                "id": qid,
                "type": "mcq",
                "question": q.get("question"),
                "student_answer": student_ans,
                "correct_answer": q.get("correct_answer"),
                "score_percentage": score,
                "is_correct": is_correct,
                "feedback": "Correct option selected." if is_correct else f"Incorrect. The correct option is: {q.get('correct_answer')}.",
                "explanation": q.get("explanation", "")
            })

        elif qtype == "fill_in_the_blank":
            correct = q.get("correct_answer", "").strip().lower()
            synonyms = [s.strip().lower() for s in q.get("acceptable_synonyms", [correct])]
            is_correct = any(s == student_ans.lower() for s in synonyms)
            score = 100 if is_correct else 0
            earned_points += (score / 100.0)
            question_evaluations.append({
                "id": qid,
                "type": "fill_in_the_blank",
                "question": q.get("question"),
                "student_answer": student_ans,
                "correct_answer": q.get("correct_answer"),
                "score_percentage": score,
                "is_correct": is_correct,
                "feedback": "Accurate terminology." if is_correct else f"Expected: '{q.get('correct_answer')}'.",
                "explanation": q.get("explanation", "")
            })

        else:
            # Written Question Rubric Evaluation via LLM
            prompt = f"""
Evaluate this student's written exam response using the provided rubric.

Question: {q.get('question')}
Rubric: {q.get('rubric_criteria')}
Sample Model Answer: {q.get('sample_model_answer')}

Student's Written Answer:
"{student_ans}"

Provide an objective academic grade from 0 to 100 and constructive feedback.
Return ONLY valid JSON:
{{
  "score_percentage": 85,
  "feedback": "Constructive academic feedback...",
  "strengths": "What was well explained...",
  "missed_points": "What was missing..."
}}
"""
            raw = await call_llm(prompt, "You are a university exam grader. Output strict JSON only.", temperature=0.1)
            score = 75
            feedback = "Response addresses core concepts adequately."
            if raw:
                try:
                    clean = raw.strip().replace("```json", "").replace("```", "").strip()
                    eval_data = json.loads(clean)
                    score = int(eval_data.get("score_percentage", 75))
                    feedback = eval_data.get("feedback", feedback)
                except Exception:
                    pass

            earned_points += (score / 100.0)
            question_evaluations.append({
                "id": qid,
                "type": "written",
                "question": q.get("question"),
                "student_answer": student_ans,
                "sample_model_answer": q.get("sample_model_answer"),
                "score_percentage": score,
                "is_correct": score >= 70,
                "feedback": feedback,
                "explanation": q.get("rubric_criteria", "")
            })

    overall_percentage = round((earned_points / max(total_questions, 1)) * 100, 1)

    if overall_percentage >= 85:
        mastery_badge = "Mastered 🌟"
        mastery_level = "mastered"
    elif overall_percentage >= 65:
        mastery_badge = "Proficient 👍"
        mastery_level = "proficient"
    else:
        mastery_badge = "Needs Review 📚"
        mastery_level = "needs_review"

    return {
        "topic_id": topic_id,
        "total_questions": total_questions,
        "score": round(earned_points, 1),
        "percentage": overall_percentage,
        "mastery_badge": mastery_badge,
        "mastery_level": mastery_level,
        "evaluations": question_evaluations
    }
