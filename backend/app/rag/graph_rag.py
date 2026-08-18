"""
Advanced GraphRAG Pipeline v2 — 4-Stage Architecture Orchestrator.

┌─────────────────────────────────────────────────────────────┐
│ Stage 1: Document Parsing & Preprocessing                   │
│   PyMuPDF → pdfplumber → pypdf → OCR → Docling             │
│   Section tree extraction + formula preservation            │
│   Semantic Chunking: 500-1000 words + Page/Header metadata  │
├─────────────────────────────────────────────────────────────┤
│ Stage 2: Embedding & Graph Extraction                       │
│   EmbeddingPipeline (Ollama / OpenAI / Gemini)             │
│   Dense Vector Embeddings + Graph Triplet Extraction        │
│   (head, relation, tail) triplets via LLM                  │
├─────────────────────────────────────────────────────────────┤
│ Stage 3: Storage & Indexing                                 │
│   FAISS HNSW vector store (replaces ChromaDB)              │
│   LightRAG JSON-KV knowledge graph (replaces NetworkX)      │
├─────────────────────────────────────────────────────────────┤
│ Stage 4: Query & Reasoning                                  │
│   Agent Query Router (chat / problem-solver)               │
│   Hybrid Search Engine (Dense + BM25 + Graph)              │
│   Context + Precise Citations (page/section/path)           │
└─────────────────────────────────────────────────────────────┘

SSE event types (unchanged API contract):
  {"type": "sources",       "data": [...]}
  {"type": "graph_context", "data": {...}}
  {"type": "confidence",    "data": {"score": 0.85, "label": "high"}}
  {"type": "token",         "data": "..."}
  {"type": "done"}
"""
import asyncio
import json
import re
from pathlib import Path
from typing import List, Dict, AsyncGenerator, Optional, Set

from app.rag.ollama_client import ollama
from app.rag.reranker import reranker
from app.rag.query_engine import (
    query_expander,
    hyde_engine,
    contextual_compressor,
    confidence_scorer,
    oos_handler,
)
from app.rag.cache import query_result_cache
from app.core.config import get_settings

# ── Stage 1: New Pipeline parsers & chunker ────────────────────────────────
from app.rag.pipeline.parser import document_parser
from app.rag.pipeline.section_tree import build_section_tree
from app.rag.pipeline.chunker import semantic_chunker

# ── Stage 2: Multi-provider embeddings + triplet extraction ───────────────
from app.rag.pipeline.embedder import embedding_pipeline
from app.rag.entity_extractor import (
    extract_graph_triplets,
    extract_entities_and_relationships,
    extract_query_entities,
)

# ── Stage 3: Active storage backends (FAISS + JSON-KV by default) ─────────
from app.rag.storage import active_vector_store, active_graph_store

# Legacy aliases kept for backward compatibility
from app.rag.graph_store import graph_store          # NetworkX fallback
from app.rag.vector_store import vector_store        # ChromaDB fallback

settings = get_settings()

# ── Convenience: route to active backends ──────────────────────────────────
_vs = active_vector_store
_gs = active_graph_store

# ── System Prompt (Pedagogical Excellence, Conceptual Rigor & Grounding) ────────
SYSTEM_PROMPT = """You are DeepTutor, an elite AI tutor that answers strictly and faithfully using the provided study material and context.
Your mission is to build deep, intuitive conceptual understanding for students while maintaining absolute factual accuracy with zero hallucinations.

==================================================
STRICT GROUNDING & ACCURACY RULES (MANDATORY)
==================================================
1. ACCURATE TEACHING FROM MATERIAL:
   - Base your answers primarily on the provided CONTEXT (Document Passages & Knowledge Graph).
   - Synthesize and explain the concepts in the context clearly, intuitively, and thoroughly.
   - Gracefully handle student spelling errors or typos (e.g., "mechanisam" -> "mechanism", "suport" -> "support").
   - ONLY if the student asks about a completely unrelated topic with zero presence or connection in the document context (e.g. asking for a recipe when the document is about machine learning), state clearly:
     "The provided material doesn't cover this — I can't answer confidently from it."

2. NO FABRICATION:
   - Never invent false formulas, fake citations, or phantom numbers not present in the context.
   - When providing an intuitive analogy or mental model to explain a concept from the text, label it: "(Example for intuition — not from source material)".

3. NO INLINE CITATION TAGS (CRITICAL):
   - Do NOT include bracketed file names, page citations, or source tags like `[ml algorithams.pdf p.4]`, `[p.4]`, or `[file.pdf]` anywhere in your response, tables, or headings.
   - Write clean, fluid, and readable prose directly. The system UI displays sources separately.

4. CLEAN MATH & TABLE FORMATTING:
   - Always ensure LaTeX equations and formulas are complete and properly closed with `$` or `$$`.
   - Never use raw unescaped vertical bars `|` inside Markdown table cells (use `\mid` or `P(c given h)` for conditional probabilities) so table columns do not break.

5. OUTPUT FORMATTING TEMPLATE (Follow this clean structure):
   # 📚 [Topic / Concept Name]

   ### 💡 Big-Picture Concept
   [Accessible, high-level definition grounded strictly in the material]

   > **Intuitive Analogy (Mental Model):**
   > *(Example for intuition — not from source material)*: [Memorable real-world analogy].

   ---

   ### 🔑 Key Concepts Breakdown
   | Concept | Core Explanation / Definition |
   | :--- | :--- |
   | **[Concept 1]** | [Clear explanation] |
   | **[Concept 2]** | [Clear explanation] |

   ---

   ### ⚙️ How It Works Step-by-Step
   1. **[Step 1 Name]:** [Clear explanation]
   2. **[Step 2 Name]:** [Clear explanation]
   3. **[Step 3 Name]:** [Clear explanation]

   ---

   ### ⚖️ Strengths vs. Limitations
   #### ✅ Strengths
   - **[Strength 1]:** [Details]
   - **[Strength 2]:** [Details]

   #### ⚠️ Limitations
   - **[Limitation 1]:** [Details]
   - **[Limitation 2]:** [Details]

   ---

   ### 📌 Summary Takeaway
   [2-3 sentence key takeaway summarizing the concept's core value]
"""


# ── 10th Standard (SSLC) Student Friendly System Prompt ───────────────────────
SSLC_STUDENT_SYSTEM_PROMPT = """You are DeepTutor, a friendly, encouraging, and expert Class 10 (SSLC) AI Tutor.
Your goal is to make learning simple, exciting, and easy to understand for 10th standard students studying Mathematics, Physics, and Chemistry from their official Kerala SCERT textbook.

==================================================
10TH GRADE TEACHING & FORMATTING GUIDELINES (MANDATORY)
==================================================
1. KEEP IT SIMPLE & ENGAGING:
   - Use clear, straightforward language that a 15-year-old high school student can understand immediately.
   - Avoid overly dense or abstract academic jargon; explain technical terms using simple words.
   - Use friendly, warm formatting with helpful emoji accents.

2. CLEAN STEP-BY-STEP WORKED EXAMPLES:
   - For Mathematics and Science calculations, always format steps cleanly as numbered items:
     1. **Step 1: [Action]:** [Explanation]
     2. **Step 2: [Action]:** [Explanation]
   - Use clean LaTeX formatting enclosed in single `$` for inline math (e.g. $a_n = a + (n-1)d$, $1/f = 1/v - 1/u$, $\text{CO}_2$) or `$$` for standalone equations.

3. STRICT GROUNDING IN TEXTBOOK:
   - Base definitions, formulas, and principles strictly on the provided Textbook Context.
   - Never hallucinate fake formulas or ungrounded facts.
   - Do NOT include bracketed file citation tags like `[file.pdf p.4]` in your text. The UI displays sources separately.

4. MANDATORY OUTPUT TEMPLATE (Follow this EXACT clean structure with headers and horizontal lines):
   # 📘 [Topic / Concept Name]

   ### 💡 Simple Definition (In Easy Words)
   [Clear, simple 2-sentence explanation of what this means in plain English]

   > 🌟 **Real-Life Example / Analogy:**  
   > *(Example for intuition — not from source material)*: [A relatable real-world analogy that makes the concept click instantly]

   ---

   ### 📝 Step-by-Step Explanation & Solved Example
   [Break down how it works in clear, easy steps or give a solved textbook numerical/example with full working]

   ---

   ### 🔑 Important Exam Points & Key Formulas
   | Key Term / Formula | What You Must Remember for the Exam |
   | :--- | :--- |
   | **[Formula / Term 1]** | [Clear explanation / must-know points] |
   | **[Formula / Term 2]** | [Clear explanation / must-know points] |

   ---

   ### 🎯 Quick Practice Question
   **Question:** [A simple, fun 1-sentence question to test the student's understanding]  
   💡 **Hint:** [1-line hint to help them solve it]
"""


def _detect_simple_casual_query(text: str) -> Optional[str]:
    """
    Fast-path zero-token response handler for simple greetings, check-ins,
    gratitude, and out-of-scope non-academic queries (like weather).
    Eliminates unnecessary LLM tokens and vector search latency.
    """
    t = text.strip().lower()
    t_clean = re.sub(r'[^a-zA-Z0-9\s]', '', t).strip()

    # 1. Greetings
    if t_clean in {
        "hi","hai","hello", "hey", "hola", "hi there", "hello there", "hey there",
        "greetings", "good morning", "good afternoon", "good evening", "howdy", "sup", "yo"
    }:
        return "Hello! 👋 I'm **DeepTutor**, your AI academic tutor. What topic or concept would you like to explore today?"

    # 2. Check-ins / Status
    if t_clean in {"how are you", "how are you doing", "hows it going", "how are things", "whats up", "how do you do"}:
        return "I'm doing great and ready to help you learn! 🚀 What subject or problem can we tackle together today?"

    # 3. Identity / Capability
    if t_clean in {
        "who are you", "what are you", "what is your name", "who made you",
        "tell me about yourself", "what can you do", "help me"
    }:
        return (
            "I'm **DeepTutor**, your AI academic tutor! 🎓 I can break down complex concepts with intuitive analogies, "
            "solve problems step-by-step, answer questions from your uploaded documents, and create practice quizzes or flashcards."
        )

    # 4. Gratitude & Farewells
    if t_clean in {"thanks", "thank you", "thank you so much", "thanks a lot", "ty", "thx", "appreciate it"}:
        return "You're very welcome! 😊 Feel free to ask whenever you have more questions. Happy studying! 📚"
    if t_clean in {"bye", "goodbye", "see you", "see ya", "cya", "have a good day", "good night"}:
        return "Goodbye! Best of luck with your studies, and come back anytime you need help! 👋"

    # 5. Non-academic queries (e.g. weather, general chit-chat)
    if any(phrase in t_clean for phrase in ["what is the weather", "how is the weather", "weather today", "weather forecast", "whats the weather"]):
        return (
            "I don't have access to live real-time weather data 🌤️, but I'm here to help you study, "
            "understand concepts, and solve any academic problems!"
        )

    if t_clean in {"test", "testing", "ping"}:
        return "DeepTutor is online and ready! 🚀 How can I help you with your studies today?"

    return None


def extract_requested_pages(text: str) -> List[int]:
    """
    Extract page numbers requested in user question.
    Handles:
    - 'explain page number 33' -> [33]
    - 'page number 94 and 95' -> [94, 95]
    - 'pages 94-96' or 'pages 94 to 96' -> [94, 95, 96]
    - 'page 94', 'page no 94', 'page no. 94', 'page #94' -> [94]
    - 'p. 94', 'p94', 'pg 94', 'pg. 94', 'pg94' -> [94]
    - '33rd page', '33th page', '33nd page', '33st page' -> [33]
    """
    if not text:
        return []
    pages: Set[int] = set()
    text_lower = text.lower()

    # 1. Page ranges: "pages 94-96", "pages 94 to 96", "p. 94-96", "pg 94-96", "page no 94-96"
    for match in re.finditer(r'(?:pages?|p\.?|pg\.?)\s*(?:numbers?|no\.?|nums?|#)?\s*(\d+)\s*(?:-|to)\s*(\d+)', text_lower):
        start, end = int(match.group(1)), int(match.group(2))
        if 0 < start <= end and (end - start) <= 50:
            pages.update(range(start, end + 1))

    # 2. Comma / and list: "pages 94, 95 and 96", "page no 94, 95", "page 94 and 95"
    for match in re.finditer(r'(?:pages?|p\.?|pg\.?)\s*(?:numbers?|no\.?|nums?|#)?\s*(\d+(?:\s*(?:,|and|&)\s*\d+)+)', text_lower):
        nums = re.findall(r'\d+', match.group(1))
        pages.update([int(n) for n in nums if int(n) > 0])

    # 3. Single page references: "page 33", "page number 33", "page no 33", "page no. 33", "page #33", "pg 33", "pg. 33", "pg33", "p. 33", "p.33", "p33"
    for match in re.finditer(r'(?:pages?|p\.?|pg\.?)\s*(?:numbers?|no\.?|nums?|#)?\s*(\d+)', text_lower):
        num = int(match.group(1))
        if num > 0:
            pages.add(num)

    # 4. Ordinal page references: "33rd page", "33th page", "33nd page", "33st page"
    for match in re.finditer(r'(\d+)(?:st|nd|rd|th)?\s+pages?', text_lower):
        num = int(match.group(1))
        if num > 0:
            pages.add(num)

    return sorted(list(pages))


# ── Chunk deduplication ─────────────────────────────────────────────────────────
def _deduplicate_chunks(chunks_lists: List[List[Dict]]) -> List[Dict]:
    """
    Merge multiple chunk lists (from query variants) with deduplication.
    Keeps the highest score for duplicate doc IDs. Preserves insertion order.
    """
    seen: Dict[str, Dict] = {}
    for chunks in chunks_lists:
        for chunk in chunks:
            cid = chunk.get("id", chunk["text"][:64])
            if cid not in seen or chunk.get("score", 0) > seen[cid].get("score", 0):
                seen[cid] = chunk
    return list(seen.values())


from app.rag.topic_sanitizer import is_valid_academic_topic, clean_and_format_topic, deduplicate_and_rank_topics


def _extract_key_topics_from_chunks(chunks: List[Dict]) -> List[str]:
    """
    Extract clean, high-yield key academic concepts from semantic chunks.
    Filters out boilerplate section headings ('Results and Discussion', 'Methodology'),
    table noise, and citations.
    """
    raw_topics: List[str] = []
    for chunk in chunks:
        meta = chunk.get("metadata", {})
        section_title = meta.get("section_title", "")
        if section_title:
            raw_topics.append(section_title)
        section_path = meta.get("section_path", "")
        if section_path:
            for part in section_path.split(" > "):
                raw_topics.append(part.strip())
    return deduplicate_and_rank_topics(raw_topics, max_topics=20)


# ══════════════════════════════════════════════════════════════════════════════
# GraphRAGPipeline
# ══════════════════════════════════════════════════════════════════════════════
class GraphRAGPipeline:
    """Main GraphRAG pipeline v2 — singleton shared across requests."""

    # ── Indexing (Stage 1 → 2 → 3) ───────────────────────────────────────────
    async def index_document(
        self,
        topic_id: str,
        file_path: str,
        progress_callback=None,
    ) -> Dict:
        """
        Full 4-stage indexing pipeline:

        Stage 1 — Parse:   DocumentParser (PyMuPDF cascade) + section tree
        Stage 1 — Chunk:   SemanticChunker (500-1000 words + metadata)
        Stage 2 — Embed:   EmbeddingPipeline (Ollama/OpenAI/Gemini)
        Stage 2 — Extract: Graph Triplets (head, relation, tail)
        Stage 3 — Store:   FAISS HNSW + LightRAG JSON-KV graph
        """
        source_name = Path(file_path).name

        # ── Stage 1a: Parse ──────────────────────────────────────────────────
        if progress_callback:
            await progress_callback("parsing", 5)

        pages = await asyncio.to_thread(document_parser.parse, file_path)
        if not pages:
            raise ValueError(
                "No text could be extracted from the document. "
                "Please verify that the PDF has selectable text and is not empty or scanned/image-only."
            )

        # ── Stage 1b: Build section tree ─────────────────────────────────────
        section_nodes = build_section_tree(pages)

        # ── Stage 1c: Semantic chunking (500-1000 words) ─────────────────────
        if progress_callback:
            await progress_callback("chunking", 15)

        chunks = semantic_chunker.chunk_pages(pages, source_name, section_nodes)
        if not chunks:
            raise ValueError("Chunking produced no results. Document may be empty or unparseable.")

        total = len(chunks)
        print(f"[PIPELINE] Stage 1 complete: {len(pages)} pages → {total} semantic chunks")

        # ── Stage 2a: Embed chunks (multi-provider) ───────────────────────────
        if progress_callback:
            await progress_callback("embedding", 25)

        embeddings = await embedding_pipeline.embed_chunks(chunks)

        if progress_callback:
            await progress_callback("embedding", 50)

        # ── Stage 3a: Store in FAISS vector store ─────────────────────────────
        _vs.add_chunks(topic_id, chunks, embeddings)

        # Invalidate query result cache for this topic (new data)
        await query_result_cache.invalidate(topic_id)

        # ── Stage 2b + 3b: Instant Key Topics & Graph Nodes ───────────────────
        all_entities: List[Dict] = []
        all_relationships: List[Dict] = []

        extracted_topics = _extract_key_topics_from_chunks(chunks)
        for topic in extracted_topics[:15]:
            all_entities.append({
                "name": topic,
                "type": "concept",
                "description": f"Key concept in {topic_id}"
            })

        _gs.add_entities(topic_id, all_entities)

        # Signal 100% to UI immediately — document is ready for chat & search
        if progress_callback:
            await progress_callback("indexing_complete", 100)

        print(f"[PIPELINE] Stage 3 complete: {total} chunks indexed in {settings.VECTOR_STORE_BACKEND} (topic: {topic_id})")

        # ── Background Deep Triplet Extraction (Non-blocking async task) ──────
        async def _background_triplet_extraction():
            try:
                sample_step = max(1, len(chunks) // 3)
                sample_chunks = chunks[::sample_step][:3]
                sem = asyncio.Semaphore(2)

                async def _extract_one(chunk: dict):
                    async with sem:
                        try:
                            source = chunk["metadata"].get("source", "")
                            page = chunk["metadata"].get("page", "")
                            section = chunk["metadata"].get("section_title", "")
                            source_info = f"{source} p.{page}" + (f" §{section}" if section else "")
                            chunk_id = f"{topic_id}_{hash(chunk['text']) % 10**8}"
                            ents, rels, trips = await extract_graph_triplets(
                                chunk["text"], source_doc=source_info, chunk_id=chunk_id
                            )
                            return ents, rels, [t.to_dict() for t in trips]
                        except Exception:
                            return [], [], []

                results = await asyncio.gather(*[_extract_one(c) for c in sample_chunks])
                bg_ents, bg_rels, bg_trips = [], [], []
                for ents, rels, trips in results:
                    bg_ents.extend(ents)
                    bg_rels.extend(rels)
                    bg_trips.extend(trips)

                if bg_ents:
                    _gs.add_entities(topic_id, bg_ents)
                if bg_rels:
                    _gs.add_relations(topic_id, bg_rels)
                if bg_trips:
                    _gs.add_triplets(topic_id, bg_trips)
            except Exception as e:
                print(f"[PIPELINE BG] Triplet extraction background error: {e}")

        # Fire and forget background triplet extraction
        asyncio.create_task(_background_triplet_extraction())

        stats = _gs.get_graph_stats(topic_id)
        return {
            "chunks_indexed": total,
            "entities_extracted": len(all_entities),
            "relationships_extracted": len(all_relationships),
            "triplets_extracted": 0,
            "graph_nodes": stats["node_count"],
            "graph_edges": stats["edge_count"],
            "extracted_topics": extracted_topics,
            "chunking_strategy": "semantic_500_1000w",
            "vector_backend": settings.VECTOR_STORE_BACKEND,
            "graph_backend": settings.GRAPH_STORE_BACKEND,
            "embed_provider": settings.EMBEDDING_PROVIDER,
        }

    # ── Retrieval ──────────────────────────────────────────────────────────────
    async def _retrieve_chunks(
        self,
        topic_id: str,
        question: str,
    ) -> List[Dict]:
        """
        Stage 4 — Advanced hybrid retrieval:
        1. Cache check
        2. Query expansion (N variants)
        3. HyDE (hypothetical doc embedding)
        4. Hybrid search (FAISS dense + BM25) via RRF fusion
        5. BM25/CrossEncoder reranking
        6. Contextual compression
        Returns final top-K chunks with precise citations.
        """
        # 1. Cache check
        cached = await query_result_cache.get(topic_id, question)
        if cached is not None:
            return cached

        # 2. Query expansion & HyDE (fast-pathed when disabled)
        if settings.ENABLE_QUERY_EXPANSION:
            query_variants = await query_expander.expand(question)
        else:
            query_variants = [question]

        if settings.ENABLE_HYDE:
            hyde_doc = await hyde_engine.generate_hypothetical_document(question)
            embed_tasks = [embedding_pipeline.embed(q) for q in query_variants] + [embedding_pipeline.embed(hyde_doc)]
            all_results = await asyncio.gather(*embed_tasks, return_exceptions=True)
            query_embeddings = [r for r in all_results[:-1] if isinstance(r, list)]
            hyde_embedding = all_results[-1] if isinstance(all_results[-1], list) else None
        else:
            hyde_doc = question
            hyde_embedding = None
            query_embeddings = await asyncio.gather(*[embedding_pipeline.embed(q) for q in query_variants])
            query_embeddings = [r for r in query_embeddings if isinstance(r, list)]

        # 5. Hybrid search for each embedding
        all_chunk_lists: List[List[Dict]] = []

        async def _hybrid_search(embedding: List[float], q_text: str) -> List[Dict]:
            return _vs.search_hybrid(
                topic_id,
                embedding,
                q_text,
                top_k=settings.TOP_K_RETRIEVAL,
            )

        search_tasks = []
        for i, emb in enumerate(query_embeddings):
            q_text = query_variants[i] if i < len(query_variants) else question
            search_tasks.append(_hybrid_search(emb, q_text))

        if hyde_embedding is not None:
            search_tasks.append(_hybrid_search(hyde_embedding, hyde_doc))

        search_results = await asyncio.gather(*search_tasks, return_exceptions=True)
        for res in search_results:
            if isinstance(res, list) and res:
                all_chunk_lists.append(res)

        # 6. Merge + deduplicate across all query variants
        merged_chunks = _deduplicate_chunks(all_chunk_lists)

        if not merged_chunks:
            return []

        # 7. Rerank
        reranked = await reranker.rerank(
            query=question,
            chunks=merged_chunks,
            top_k=settings.TOP_K_CHUNKS,
        )

        # 8. Contextual compression
        compressed = await contextual_compressor.compress(
            query=question,
            chunks=reranked,
            mode="keyword",  # Fast mode; use "llm" for max precision
        )

        # Cache the result
        await query_result_cache.set(topic_id, question, compressed)

        return compressed

    # ── Query stream ───────────────────────────────────────────────────────────
    async def query_stream(
        self,
        topic_id: Optional[str],
        question: str,
        session_messages: List[Dict],
    ) -> AsyncGenerator[str, None]:
        """
        Full advanced GraphRAG query with SSE streaming.

        Yields JSON-encoded SSE events:
          {"type": "sources",       "data": [...]}
          {"type": "graph_context", "data": {...}}
          {"type": "confidence",    "data": {"score": 0.85, "label": "high"}}
          {"type": "token",         "data": "..."}
          {"type": "done"}
        """
        # ── Fast-path: Instant zero-token response for simple greetings / casual queries
        quick_resp = _detect_simple_casual_query(question)
        if quick_resp:
            for word in quick_resp.split(" "):
                yield f"data: {json.dumps({'type': 'token', 'data': word + ' '})}\n\n"
            yield f"data: {json.dumps({'type': 'done'})}\n\n"
            return

        vector_chunks: List[Dict] = []
        graph_context_data: Dict = {"entities": [], "relationships": []}
        graph_context_text = ""
        vector_context_text = ""
        effective_topic_id = topic_id or ""

        # ── Step 1: Retrieval ──────────────────────────────────────────────────
        requested_pages = extract_requested_pages(question)

        if effective_topic_id:
            if requested_pages:
                # Direct exact page metadata filter — retrieve page chunks directly
                page_chunks = _vs.get_chunks_by_pages(effective_topic_id, requested_pages)
                # Fallback to base topic if namespaced topic had no chunks
                if not page_chunks and "_" in effective_topic_id:
                    fallback_id = effective_topic_id.split("_", 2)[-1]
                    page_chunks = _vs.get_chunks_by_pages(fallback_id, requested_pages)

                if page_chunks:
                    vector_chunks = page_chunks
                    # Also attempt lightweight graph context retrieval
                    try:
                        graph_context_data = _gs.get_entity_context_for_query(
                            effective_topic_id,
                            question,
                            hop_depth=1,
                        )
                    except Exception:
                        graph_context_data = {"entities": [], "relations": [], "triplets": [], "context_text": ""}
                else:
                    missing_str = ", ".join([str(p) for p in requested_pages])
                    missing_msg = (
                        f"### 📄 Page {missing_str} Not Found in Document\n\n"
                        f"I checked your uploaded study material, but **Page {missing_str}** was not found or has no extractable text.\n\n"
                        f"---\n\n"
                        f"**💡 Suggestions:**\n"
                        f"- Check the total page count of your uploaded document.\n"
                        f"- Try asking for a different page number (e.g. *\"Explain page 1\"*).\n"
                        f"- You can also ask directly about any concept by name (e.g. *\"What is Support Vector Machines?\"*)."
                    )
                    for word in missing_msg.split(" "):
                        yield f"data: {json.dumps({'type': 'token', 'data': word + ' '})}\n\n"
                    yield f"data: {json.dumps({'type': 'done'})}\n\n"
                    return

            elif _vs.count(effective_topic_id) > 0:
                # Parallelize vector retrieval & graph retrieval
                async def _get_vector_task():
                    return await self._retrieve_chunks(effective_topic_id, question)

                async def _get_graph_task():
                    # Instant in-memory entity & triplet matching (<1ms)
                    try:
                        return _gs.get_entity_context_for_query(
                            effective_topic_id,
                            question,
                            hop_depth=settings.GRAPH_HOP_DEPTH,
                        )
                    except Exception:
                        return {"entities": [], "relations": [], "triplets": [], "context_text": ""}

                vector_chunks, graph_context_data = await asyncio.gather(
                    _get_vector_task(),
                    _get_graph_task(),
                )

            # Build text representations (for page queries, include all page chunks up to top 6)
            if vector_chunks:
                top_chunks = vector_chunks[:6] if requested_pages else vector_chunks[:settings.TOP_K_CHUNKS]
                vector_context_text = "\n\n".join([
                    f"[{c['metadata'].get('source', 'doc')} p.{c['metadata'].get('page', '')}]"
                    + (f" §{c['metadata'].get('section_title', '')}" if c['metadata'].get('section_title') else "")
                    + f"\n{c['text'][:2000]}"
                    for c in top_chunks
                ])

            # Use pre-formatted context_text from JSON-KV graph store
            if graph_context_data.get("context_text"):
                graph_context_text = graph_context_data["context_text"]
            elif graph_context_data.get("entities"):
                graph_context_text = "Entities:\n" + "\n".join([
                    f"- {n.get('name', n.get('id', ''))} ({n.get('type', 'concept')}): {n.get('description', '')}"
                    for n in graph_context_data["entities"]
                ])
                if graph_context_data.get("triplets"):
                    graph_context_text += "\n\nRelationships:\n" + "\n".join([
                        f"- {t.get('head', '')} --[{t.get('relation', '')}]--> {t.get('tail', '')}"
                        for t in graph_context_data["triplets"]
                    ])
                elif graph_context_data.get("relations"):
                    graph_context_text += "\n\nRelationships:\n" + "\n".join([
                        f"- {e.get('source_entity', '')} \u2192 {e.get('target_entity', '')} ({e.get('type', '')})"
                        for e in graph_context_data["relations"]
                    ])

        # ── Step 2: Confidence scoring + out-of-scope detection ───────────────
        if requested_pages and vector_chunks and not any("system_notice" in str(c.get("id", "")) for c in vector_chunks):
            confidence_score, confidence_label = 1.0, "high"
        else:
            confidence_score, confidence_label = confidence_scorer.score(
                chunks=vector_chunks,
                graph_entities=graph_context_data.get("entities", []),
                query=question,
            )

        # ── Step 3: Emit SSE events ────────────────────────────────────────────
        if vector_chunks:
            sources_payload = [
                {
                    "doc": c["metadata"].get("source", "document"),
                    "page": c["metadata"].get("page", 1),
                    "section": c["metadata"].get("section_title", ""),
                    "score": c.get("rerank_score", c["score"]),
                    "text": c["text"][:300] + "..." if len(c["text"]) > 300 else c["text"],
                }
                for c in vector_chunks
            ]
            yield f"data: {json.dumps({'type': 'sources', 'data': sources_payload})}\n\n"

        if graph_context_data["entities"]:
            yield f"data: {json.dumps({'type': 'graph_context', 'data': graph_context_data})}\n\n"

        # Emit confidence score
        yield f"data: {json.dumps({'type': 'confidence', 'data': {'score': confidence_score, 'label': confidence_label}})}\n\n"

        # ── Step 4: Out-of-scope handling ──────────────────────────────────────
        is_textbook = bool(effective_topic_id and effective_topic_id.startswith(("sslc-", "math-", "phys-", "chem-", "textbook")))
        if effective_topic_id and not is_textbook and oos_handler.is_out_of_scope(confidence_score, confidence_label):
            oos_response = oos_handler.format_response(question, is_textbook=False)
            for token in oos_response.split(" "):
                yield f"data: {json.dumps({'type': 'token', 'data': token + ' '})}\n\n"
            yield f"data: {json.dumps({'type': 'done'})}\n\n"
            return

        # ── Step 5: Build LLM messages ─────────────────────────────────────────
        is_textbook = bool(effective_topic_id and effective_topic_id.startswith(("sslc-", "math-", "phys-", "chem-", "textbook")))
        history_text = ""
        for msg in session_messages[-6:]:
            role_label = "Student" if msg["role"] == "user" else "Tutor"
            history_text += f"{role_label}: {msg['content'][:500]}\n"

        requested_pages_list = extract_requested_pages(question) if question else []
        q_lower = question.lower() if question else ""

        if (requested_pages_list and vector_chunks and
                not any("Missing" in str(c.get("metadata", {}).get("page", "")) for c in vector_chunks)):
            pages_str = ", ".join(str(p) for p in requested_pages_list)
            prompt_instruction = (
                f"The student specifically asked for an explanation of Page {pages_str}.\n"
                f"Explain and summarize ALL concepts, definitions, formulas, workflows, and details presented on Page {pages_str} thoroughly, clearly, and faithfully based on the Document Context.\n"
                f"Structure your response starting with:\n"
                f"# 📄 Page {pages_str} Explanation & Summary\n\n"
                f"Follow with clear conceptual explanations, structured breakdown tables/steps, and key takeaways from that page."
            )
        elif any(w in q_lower for w in ["bullet point", "bullet points", "5-7 clear", "quick revision", "summarize into"]):
            prompt_instruction = (
                "The student specifically asked for bullet points. "
                "Provide ONLY a crisp, high-yield summary formatted as 5 to 7 structured bullet points with bold key terms. "
                "Do NOT include unrelated filler, extra analogies, or full article sections."
            )
        elif any(w in q_lower for w in ["important point", "important points", "exam-critical", "exam points", "core formulas"]):
            prompt_instruction = (
                "The student specifically asked for important exam-critical points. "
                "Provide a focused high-yield breakdown: (1) Core Definitions & Must-Know Formulas, "
                "(2) Crucial Exam Points, and (3) Common Misconceptions / Pitfalls to avoid."
            )
        elif any(w in q_lower for w in ["analogy", "intuitive analogy", "simple analogy", "mental model"]):
            prompt_instruction = (
                "The student specifically asked for a simple analogy. "
                "Explain the topic using an intuitive, memorable real-world analogy and visual mental model, "
                "followed by a brief 2-sentence connection to the technical concept."
            )
        else:
            if is_textbook:
                prompt_instruction = (
                    "Please explain this topic in an easy, friendly, and structured way for a 10th class student following the 10th Grade Output Template: "
                    "(1) # 📘 [Topic Title], (2) 💡 Simple Definition (In Easy Words), "
                    "(3) 🌟 Real-Life Example / Analogy in a blockquote, (4) 📝 Step-by-Step Explanation & Solved Example (with clear calculations), "
                    "(5) 🔑 Important Exam Points & Key Formulas (table), and (6) 🎯 Quick Practice Question with a Hint."
                )
            else:
                prompt_instruction = (
                    "Please explain this topic clearly and educationally for a student following the Output Formatting Template: "
                    "(1) # 📚 [Topic Title], (2) 💡 Big-Picture Concept + Blockquote Intuitive Analogy, "
                    "(3) 🔑 Key Concepts Breakdown Table, (4) ⚙️ How It Works Step-by-Step with numbered steps, "
                    "(5) ⚖️ Strengths vs. Limitations (with ✅ and ⚠️ subheadings), and (6) 📌 Summary Takeaway."
                )

        if graph_context_text or vector_context_text:
            user_content = (
                f"## Knowledge Graph Context\n"
                f"Relevant entities and relationships retrieved from the knowledge graph:\n"
                f"{graph_context_text or 'No graph entities found for this query.'}\n\n"
                f"## Document Context\n"
                f"Relevant passages from uploaded documents:\n"
                f"{vector_context_text or 'No document passages found for this query.'}\n\n"
                f"## Conversation History\n"
                f"{history_text or 'No prior conversation.'}\n\n"
                f"## Student Question\n"
                f"{question}\n\n"
                f"## Instructions\n"
                f"1. Focus exclusively on answering the immediate Student Question ('{question}').\n"
                f"2. Do NOT repeat or continue explaining unrelated topics from Conversation History.\n"
                f"3. Using the Document Context and Knowledge Graph as your primary reference: {prompt_instruction}\n"
                f"4. Do NOT include bracketed file names or page numbers like [file.pdf p.4] or [p.4] anywhere in the response text. The UI displays sources separately.\n"
                f"5. If the Student Question is completely unrelated to anything in the Document Context, state: 'The provided material doesn't cover this — I can't answer confidently from it.' Otherwise, explain the concept thoroughly from the context."
            )
        else:
            user_content = (
                f"## Student Question\n"
                f"{question}\n\n"
                f"## Instructions\n"
                f"1. Focus exclusively on answering the immediate Student Question ('{question}').\n"
                f"2. Do NOT include bracketed file names or page numbers like [file.pdf p.4] or [p.4] anywhere in the response text.\n"
                f"3. {prompt_instruction}"
            )

        system_prompt_to_use = SSLC_STUDENT_SYSTEM_PROMPT if is_textbook else SYSTEM_PROMPT

        messages = [
            {"role": "system", "content": system_prompt_to_use},
            {"role": "user", "content": user_content},
        ]

        # ── Step 6: Stream tokens & verify Self-RAG grounding ──────────────────
        from app.rag.hallucination_guard import verify_response_grounding

        accumulated_text = ""
        async for token in ollama.stream(messages):
            accumulated_text += token
            yield f"data: {json.dumps({'type': 'token', 'data': token})}\n\n"

        # Step 7: Self-RAG Hallucination Guard verification (non-blocking async thread)
        grounding = await asyncio.to_thread(verify_response_grounding, accumulated_text, vector_chunks)
        yield f"data: {json.dumps({'type': 'grounding', 'data': grounding})}\n\n"

        yield f"data: {json.dumps({'type': 'done'})}\n\n"

    async def simple_query(
        self,
        topic_id: Optional[str],
        question: str,
        session_messages: List[Dict],
    ) -> Dict:
        """Non-streaming version — collects full response."""
        full_text = ""
        sources = []
        graph_data = {}
        confidence = {}

        async for event_str in self.query_stream(topic_id, question, session_messages):
            if not event_str.startswith("data: "):
                continue
            try:
                event = json.loads(event_str[6:])
                if event["type"] == "token":
                    full_text += event["data"]
                elif event["type"] == "sources":
                    sources = event["data"]
                elif event["type"] == "graph_context":
                    graph_data = event["data"]
                elif event["type"] == "confidence":
                    confidence = event["data"]
            except Exception:
                pass

        return {
            "content": full_text,
            "sources": sources,
            "graph_context": graph_data,
            "confidence": confidence,
        }


# Singleton pipeline
graph_rag = GraphRAGPipeline()
