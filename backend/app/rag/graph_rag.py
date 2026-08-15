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
1. GROUNDING ONLY:
   - Base every factual claim strictly on the provided CONTEXT (Document Passages & Knowledge Graph).
   - Do NOT use outside/general knowledge to fill gaps or speculate, even if you "know" the answer.
   - If the provided context does not contain enough information to answer, state clearly:
     "The provided material doesn't cover this — I can't answer confidently from it."

2. NO FABRICATION:
   - Never invent facts, numbers, formulas, papers, APIs, or citations not present in the context.
   - Never invent page numbers, section names, or sources unless they appear in the context.
   - If asked for something not in the context (e.g., "give a simple analogy" or "give an example"), you may provide an intuitive pedagogical example, but you MUST label it clearly: "(Example for intuition — not from source material)".

3. CITE YOUR SOURCE:
   - After each factual claim or explanation, indicate where it came from, e.g., [p.12] or [Section: Support Vector Machines].
   - If multiple context chunks are provided, cite each relevant page/section.

4. EXPRESS UNCERTAINTY HONESTLY:
   - If the context is ambiguous, partial, or conflicting, say so instead of resolving it blindly.
   - Use calibrated language: "The document states..." vs "The document suggests...".

5. NO SILENT ASSUMPTIONS:
   - If a question requires an assumption not supported by context, state the assumption explicitly rather than stating it as established fact.

6. SELF-CHECK & STUDENT PEDAGOGY:
   - Make explanations simple, accessible, and structured for student learning:
     * 💡 Simple Big-Picture Concept (intuitive and accessible)
     * 🔑 Key Concepts Breakdown (clean bullet points or tables)
     * ⚙️ How It Works Step-by-Step (logical mechanism)
     * 📌 Key Takeaway (1-2 memorable summary sentences)
   - Ensure every factual claim is strictly traceable to the provided context before outputting.
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
        "hi", "hello", "hey", "hola", "hi there", "hello there", "hey there",
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
    - 'page number 94 and 95' -> [94, 95]
    - 'pages 94-96' or 'pages 94 to 96' -> [94, 95, 96]
    - 'page 94' -> [94]
    - 'p. 94', 'p94' -> [94]
    """
    pages: Set[int] = set()
    text_lower = text.lower()

    range_pattern = r'(?:pages?|p\.?)\\s*(?:numbers?|no\\.?|nums?)?\\s*(\\d+)\\s*(?:-|to)\\s*(\\d+)'
    for match in re.finditer(r'(?:pages?|p\.?)\s*(?:numbers?|no\.?|nums?)?\s*(\d+)\s*(?:-|to)\s*(\d+)', text_lower):
        start, end = int(match.group(1)), int(match.group(2))
        if start <= end and (end - start) <= 50:
            pages.update(range(start, end + 1))

    for match in re.finditer(r'(?:pages?|p\.?)\s*(?:numbers?|no\.?|nums?)?\s*(\d+(?:\s*(?:,|and|&)\s*\d+)+)', text_lower):
        nums = re.findall(r'\d+', match.group(1))
        pages.update([int(n) for n in nums])

    for match in re.finditer(r'(?:pages?|p\.?)\s*(?:numbers?|no\.?|nums?)?\s*(\d+)', text_lower):
        pages.add(int(match.group(1)))

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


def _extract_key_topics_from_chunks(chunks: List[Dict]) -> List[str]:
    """
    Extract key topics from semantic chunks using section titles and headings.
    Replaces extract_key_topics() from the legacy document_processor module.
    """
    topics: List[str] = []
    seen: set = set()
    for chunk in chunks:
        meta = chunk.get("metadata", {})
        section_title = meta.get("section_title", "")
        if section_title and len(section_title) >= 3 and section_title.lower() not in seen:
            seen.add(section_title.lower())
            topics.append(section_title)
        section_path = meta.get("section_path", "")
        if section_path and section_path not in topics:
            for part in section_path.split(" > "):
                part = part.strip()
                if part and part.lower() not in seen and len(part) >= 3:
                    seen.add(part.lower())
                    topics.append(part)
    return topics[:25]


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

        # Signal 100% to UI — document is immediately ready for chat RAG
        if progress_callback:
            await progress_callback("indexing_complete", 100)

        print(f"[PIPELINE] Stage 3 complete: {total} chunks indexed in FAISS (topic: {topic_id})")

        # ── Stage 2b + 3b: Graph Triplet Extraction (non-blocking background) ─
        all_entities: List[Dict] = []
        all_relationships: List[Dict] = []
        all_triplets = []

        # Heuristic key topics from section headings (instant, no LLM)
        extracted_topics = _extract_key_topics_from_chunks(chunks)
        for topic in extracted_topics[:15]:
            all_entities.append({
                "name": topic,
                "type": "concept",
                "description": f"Key concept in {topic_id}"
            })

        # Sample representative chunks for deep LLM triplet extraction
        sample_step = max(1, len(chunks) // 3)
        sample_chunks = chunks[::sample_step][:3]

        semaphore = asyncio.Semaphore(3)

        async def _sem_extract(chunk: dict, index: int):
            async with semaphore:
                try:
                    source = chunk["metadata"].get("source", "")
                    page = chunk["metadata"].get("page", "")
                    section = chunk["metadata"].get("section_title", "")
                    source_info = f"{source} p.{page}" + (f" \u00a7{section}" if section else "")
                    chunk_id = f"{topic_id}_{hash(chunk['text']) % 10**8}"
                    entities, relationships, triplets = await extract_graph_triplets(
                        chunk["text"], source_doc=source_info, chunk_id=chunk_id
                    )
                    if progress_callback:
                        pct = 60 + int(((index + 1) / max(1, len(sample_chunks))) * 30)
                        await progress_callback("extracting_triplets", min(90, pct))
                    return entities, relationships, [t.to_dict() for t in triplets]
                except Exception:
                    return [], [], []

        tasks = [_sem_extract(chunk, idx) for idx, chunk in enumerate(sample_chunks)]
        results = await asyncio.gather(*tasks)

        for entities, relationships, triplets in results:
            all_entities.extend(entities)
            all_relationships.extend(relationships)
            all_triplets.extend(triplets)

        # ── Stage 3b: Store entities, relations, triplets in JSON-KV graph ───
        _gs.add_entities(topic_id, all_entities)
        _gs.add_relations(topic_id, all_relationships)
        _gs.add_triplets(topic_id, all_triplets)

        # Key topics for DB metadata
        extracted_topics = _extract_key_topics_from_chunks(chunks)
        top_entity_names = [
            e["name"] for e in all_entities
            if e.get("type") not in {"metadata"} and 4 <= len(e.get("name", "")) <= 45
        ]
        for ent_name in top_entity_names:
            if ent_name and ent_name not in extracted_topics and len(extracted_topics) < 25:
                extracted_topics.append(ent_name)

        stats = _gs.get_graph_stats(topic_id)
        if progress_callback:
            await progress_callback("done", 100)

        return {
            "chunks_indexed": total,
            "entities_extracted": len(all_entities),
            "relationships_extracted": len(all_relationships),
            "triplets_extracted": len(all_triplets),
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

        # 2. Query expansion
        query_variants = await query_expander.expand(question)

        # 3. HyDE
        hyde_task = hyde_engine.generate_hypothetical_document(question)

        # 4. Embed all query variants + HyDE doc concurrently
        embed_tasks = [embedding_pipeline.embed(q) for q in query_variants]
        all_tasks = [hyde_task] + embed_tasks
        all_results = await asyncio.gather(*all_tasks, return_exceptions=True)

        hyde_doc = all_results[0] if isinstance(all_results[0], str) else question
        query_embeddings = [
            r for r in all_results[1:]
            if isinstance(r, list)
        ]

        # Embed the HyDE hypothetical document
        if settings.ENABLE_HYDE and hyde_doc != question:
            try:
                hyde_embedding = await embedding_pipeline.embed(hyde_doc)
            except Exception:
                hyde_embedding = query_embeddings[0] if query_embeddings else None
        else:
            hyde_embedding = None

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
        if effective_topic_id and _vs.count(effective_topic_id) > 0:
            requested_pages = extract_requested_pages(question)

            if requested_pages:
                # Direct exact page metadata filter — skips vector search completely
                page_chunks = _vs.get_chunks_by_pages(effective_topic_id, requested_pages)
                if page_chunks:
                    vector_chunks = page_chunks
                else:
                    missing_str = ", ".join([str(p) for p in requested_pages])
                    vector_chunks = [{
                        "id": "system_notice",
                        "text": (
                            f"[SYSTEM NOTICE: Page(s) {missing_str} do not exist in the uploaded document. "
                            f"No content could be retrieved for page(s) {missing_str}.]"
                        ),
                        "metadata": {"source": "System", "page": f"Page Missing ({missing_str})"},
                        "score": 1.0,
                    }]
            else:
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

            # Build text representations (focused on top 3 most relevant chunks for fast prefill)
            if vector_chunks:
                top_chunks = vector_chunks[:settings.TOP_K_CHUNKS]
                vector_context_text = "\n\n".join([
                    f"[{c['metadata'].get('source', 'doc')} p.{c['metadata'].get('page', '')}]"
                    + (f" §{c['metadata'].get('section_title', '')}" if c['metadata'].get('section_title') else "")
                    + f"\n{c['text'][:1200]}"
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
        if effective_topic_id and oos_handler.is_out_of_scope(confidence_score, confidence_label):
            oos_response = oos_handler.format_response(question)
            for token in oos_response.split(" "):
                yield f"data: {json.dumps({'type': 'token', 'data': token + ' '})}\n\n"
            yield f"data: {json.dumps({'type': 'done'})}\n\n"
            return

        # ── Step 5: Build LLM messages ─────────────────────────────────────────
        history_text = ""
        for msg in session_messages[-6:]:
            role_label = "Student" if msg["role"] == "user" else "Tutor"
            history_text += f"{role_label}: {msg['content'][:500]}\n"

        requested_pages_list = extract_requested_pages(question) if question else []
        if (requested_pages_list and vector_chunks and
                not any("Missing" in str(c.get("metadata", {}).get("page", "")) for c in vector_chunks)):
            pages_str = ", ".join(str(p) for p in requested_pages_list)
            prompt_instruction = (
                f"Answer using ONLY the following content from page {pages_str}.\n"
                f"Begin your answer by clearly stating you are describing page {pages_str}."
            )
        # Determine dynamic response format based on student request / tool mode
        q_lower = question.lower() if question else ""
        if any(w in q_lower for w in ["bullet point", "bullet points", "5-7 clear", "quick revision", "summarize into"]):
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
            prompt_instruction = (
                "Please explain this topic clearly and educationally for a student. "
                "Structure the explanation with an intuitive real-world analogy, a clean concepts breakdown (using a table or bullet points), "
                "how it works step-by-step, advantages & limitations, and a concise summary takeaway."
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
                f"4. If the Student Question asks about a topic not mentioned in the Document Context, state clearly: 'The provided material doesn't cover this — I can't answer confidently from it.'"
            )
        else:
            user_content = (
                f"## Student Question\n"
                f"{question}\n\n"
                f"## Instructions\n"
                f"1. Focus exclusively on answering the immediate Student Question ('{question}').\n"
                f"2. {prompt_instruction}"
            )

        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
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
