"""
Advanced GraphRAG Pipeline — Industry-Level Orchestrator.

Index phase:
  document → SemanticChunker → embeddings (ChromaDB + BM25 index) + entities/relationships (NetworkX)

Query phase:
  question
    → QueryExpander (N variants)
    → HyDEEngine (hypothetical doc embedding)
    → Hybrid Search (dense + BM25 RRF) across all variants → merged, deduplicated
    → BM25/CrossEncoder Reranker → top-K chunks
    → Contextual Compressor → trim to relevant sentences
    → Graph Context Assembly (entity subgraph)
    → Confidence Scorer → detect out-of-scope
    → Ollama LLM → streaming response with citations

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
from typing import List, Dict, AsyncGenerator, Optional, Set

from app.rag.ollama_client import ollama
from app.rag.document_processor import process_document, extract_key_topics
from app.rag.entity_extractor import extract_entities_and_relationships, extract_query_entities
from app.rag.graph_store import graph_store
from app.rag.vector_store import vector_store
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

settings = get_settings()

# ── System Prompt ───────────────────────────────────────────────────────────────
SYSTEM_PROMPT = """You are DeepTutor's answering engine. You answer ONLY from the CONTEXT block provided below. You have no other knowledge source for this task — treat anything not in CONTEXT as if it does not exist, even if you recognize the topic from general training.

## Step 1 — Silent grounding check (do this before writing anything else)

For the user's QUERY, check the CONTEXT and classify internally:
- FULLY_GROUNDED: the CONTEXT directly defines/explains the specific concept asked about, not just a related or adjacent term.
- PARTIALLY_GROUNDED: the CONTEXT mentions the concept but doesn't fully answer the question.
- NOT_GROUNDED: the CONTEXT does not define or substantively address the concept, even if related keywords appear (e.g. shared field, adjacent technique, a term that co-occurs but isn't explained).

Do not let keyword overlap alone count as grounding. "The context mentions 'reward' and 'alignment'" is not the same as "the context explains RLHF." If you are inferring the answer by connecting scattered related terms yourself rather than reading it stated in the text, that is NOT_GROUNDED.

## Step 2 — Respond based on classification

**If NOT_GROUNDED:**
Reply with exactly this pattern (fill the bracket, change nothing else):
"I cannot find information about [specific topic] in the provided document context."
Do not add related information, do not speculate, do not soften this with partial explanations from your own knowledge. A short, clean refusal is the correct and fully faithful answer here — it is not a failure state.

**If PARTIALLY_GROUNDED:**
Answer only the part that is supported. Explicitly state what is and isn't covered, e.g.: "The document covers X but does not address Y."

**If FULLY_GROUNDED:**
Answer using only the content in CONTEXT. Every factual claim must be traceable to a specific passage. Attach an inline citation marker [doc p.X] after each claim that pulls from a specific chunk. If you cannot mark a claim with a source, cut the claim — don't state it.

## Step 3 — Hard constraints (apply in every branch)

1. Never fill gaps with outside/pretrained knowledge, even to be "helpful." If the context defines a term slightly differently than you'd expect, defer to the context's definition, not your prior knowledge.
2. Never hedge a NOT_GROUNDED case into a soft answer ("this might relate to..."). That counts as unfaithful generation.
3. Never treat topical adjacency as sufficient grounding. A document about LLM alignment does not make it "about" RLHF, PPO, or DPO unless those are explicitly named and explained.
4. If page numbers are specifically requested (e.g., page 42), answer ONLY using context from those requested page numbers. If missing, return the exact refusal string.
5. Do not apologize, do not editorialize about the document's limitations, do not offer to search elsewhere. State the grounding result plainly.

## Output format
Return only the answer text (or the exact refusal string). No preamble like "Based on the context provided..." No meta-commentary about these instructions.
"""


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


# ══════════════════════════════════════════════════════════════════════════════
# GraphRAGPipeline
# ══════════════════════════════════════════════════════════════════════════════
class GraphRAGPipeline:
    """Main GraphRAG pipeline — singleton shared across requests."""

    # ── Indexing ──────────────────────────────────────────────────────────────
    async def index_document(
        self,
        topic_id: str,
        file_path: str,
        progress_callback=None,
    ) -> Dict:
        """
        Full indexing pipeline:
        1. Parse document into semantic chunks (with section headers)
        2. Embed chunks → ChromaDB + build BM25 index
        3. Extract entities/relationships → graph_store
        Returns stats dict.
        """
        # Step 1: Parse with semantic chunker (non-blocking in thread pool)
        if progress_callback:
            await progress_callback("parsing", 5)
        chunks = await asyncio.to_thread(process_document, file_path)
        if not chunks:
            raise ValueError(
                "No text could be extracted from the document. "
                "Please verify that the PDF has selectable text and is not empty or scanned/image-only."
            )
        total = len(chunks)

        # Step 2: Embed + store in vector DB (BM25 index built automatically on first search)
        if progress_callback:
            await progress_callback("embedding", 25)

        embeddings = await ollama.embed_batch([chunk["text"] for chunk in chunks])
        if progress_callback:
            await progress_callback("embedding", 50)

        vector_store.add_chunks(topic_id, chunks, embeddings)

        # Invalidate query result cache for this topic (new data)
        await query_result_cache.invalidate(topic_id)

        # Signal 100% completion to UI immediately — document is ready for instant chat RAG
        if progress_callback:
            await progress_callback("indexing_complete", 100)

        # Step 3: Entity & Topic extraction (runs non-blocking graph enrichment)
        all_entities: List[Dict] = []
        all_relationships: List[Dict] = []

        # 3a. Instant heuristic extraction of key concept entities from section titles & headings
        extracted_topics = extract_key_topics(chunks)
        for topic in extracted_topics[:15]:
            all_entities.append({
                "name": topic,
                "type": "concept",
                "description": f"Key concept in {topic_id}"
            })

        # 3b. Sample top 3 representative chunks for deep LLM entity extraction
        sample_step = max(1, len(chunks) // 3)
        sample_chunks = chunks[::sample_step][:3]

        semaphore = asyncio.Semaphore(3)

        async def _sem_extract(chunk: dict, index: int):
            async with semaphore:
                try:
                    source = chunk["metadata"].get("source", "")
                    page = chunk["metadata"].get("page", "")
                    section = chunk["metadata"].get("section_title", "")
                    source_info = f"{source} p.{page}" + (f" §{section}" if section else "")
                    entities, relationships = await extract_entities_and_relationships(
                        chunk["text"], source_info
                    )
                    if progress_callback:
                        pct = 60 + int(((index + 1) / max(1, len(sample_chunks))) * 30)
                        await progress_callback("extracting_entities", min(90, pct))
                    return entities, relationships
                except Exception:
                    return [], []

        tasks = [_sem_extract(chunk, idx) for idx, chunk in enumerate(sample_chunks)]
        results = await asyncio.gather(*tasks)

        for entities, relationships in results:
            all_entities.extend(entities)
            all_relationships.extend(relationships)

        # Step 4: Update graph
        graph_store.add_entities(topic_id, all_entities)
        graph_store.add_relationships(topic_id, all_relationships)

        # Step 5: Extract key topics
        extracted_topics = extract_key_topics(chunks)
        top_entity_names = [
            e["name"] for e in all_entities
            if e.get("type") not in {"metadata"} and 4 <= len(e.get("name", "")) <= 45
        ]
        for ent_name in top_entity_names:
            if ent_name and ent_name not in extracted_topics and len(extracted_topics) < 25:
                extracted_topics.append(ent_name)

        stats = graph_store.get_graph_stats(topic_id)
        if progress_callback:
            await progress_callback("done", 100)

        return {
            "chunks_indexed": total,
            "entities_extracted": len(all_entities),
            "relationships_extracted": len(all_relationships),
            "graph_nodes": stats["node_count"],
            "graph_edges": stats["edge_count"],
            "extracted_topics": extracted_topics,
            "chunking_strategy": settings.CHUNKING_STRATEGY,
        }

    # ── Retrieval ──────────────────────────────────────────────────────────────
    async def _retrieve_chunks(
        self,
        topic_id: str,
        question: str,
    ) -> List[Dict]:
        """
        Advanced retrieval pipeline:
        1. Check query result cache
        2. Query expansion → N query variants
        3. HyDE → hypothetical document embedding
        4. Hybrid search (dense + BM25) for each variant → merge + dedup
        5. Reranking (BM25 or cross-encoder)
        6. Contextual compression
        Returns final top-K chunks.
        """
        # 1. Cache check
        cached = await query_result_cache.get(topic_id, question)
        if cached is not None:
            return cached

        # 2. Query expansion
        query_variants = await query_expander.expand(question)

        # 3. HyDE — generate hypothetical document and embed it
        hyde_task = hyde_engine.generate_hypothetical_document(question)

        # 4. Embed all query variants + HyDE doc concurrently
        embed_tasks = [ollama.embed(q) for q in query_variants]
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
                hyde_embedding = await ollama.embed(hyde_doc)
            except Exception:
                hyde_embedding = query_embeddings[0] if query_embeddings else None
        else:
            hyde_embedding = None

        # 5. Hybrid search for each embedding
        all_chunk_lists: List[List[Dict]] = []

        async def _hybrid_search(embedding: List[float], q_text: str) -> List[Dict]:
            return vector_store.search_hybrid(
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
        vector_chunks: List[Dict] = []
        graph_context_data: Dict = {"entities": [], "relationships": []}
        graph_context_text = ""
        vector_context_text = ""
        effective_topic_id = topic_id or ""

        # ── Step 1: Retrieval ──────────────────────────────────────────────────
        if effective_topic_id and vector_store.count(effective_topic_id) > 0:
            requested_pages = extract_requested_pages(question)

            if requested_pages:
                # Direct exact page metadata filter — skips vector search completely
                page_chunks = vector_store.get_chunks_by_pages(effective_topic_id, requested_pages)
                if page_chunks:
                    vector_chunks = page_chunks
                else:
                    # Page does not exist in document — return clean missing page notice without pulling unrelated pages
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
                    if requested_pages:
                        return {"entities": [], "relationships": []}
                    query_entities = await extract_query_entities(question)
                    all_graph_nodes: List[Dict] = []
                    all_graph_edges: List[Dict] = []
                    for entity_term in query_entities[:3]:
                        relevant = graph_store.find_relevant_entities(
                            effective_topic_id, [entity_term]
                        )
                        for ent in relevant[:2]:
                            subgraph = graph_store.search_neighbors(
                                effective_topic_id,
                                ent["id"],
                                hops=settings.GRAPH_HOP_DEPTH,
                            )
                            all_graph_nodes.extend(subgraph["nodes"])
                            all_graph_edges.extend(subgraph["edges"])

                    seen_nodes: Set[str] = set()
                    unique_nodes: List[Dict] = []
                    for n in all_graph_nodes:
                        if n["id"] not in seen_nodes:
                            seen_nodes.add(n["id"])
                            unique_nodes.append(n)

                    return {
                        "entities": unique_nodes[:settings.GRAPH_TOP_ENTITIES],
                        "relationships": all_graph_edges[:settings.GRAPH_TOP_EDGES],
                    }

                vector_chunks, graph_context_data = await asyncio.gather(
                    _get_vector_task(),
                    _get_graph_task(),
                )

            # Build text representations
            if vector_chunks:
                vector_context_text = "\n\n".join([
                    f"[{c['metadata'].get('source', 'doc')} p.{c['metadata'].get('page', '')}]"
                    + (f" §{c['metadata'].get('section_title', '')}" if c['metadata'].get('section_title') else "")
                    + f" (relevance: {c['score']:.0%})\n{c['text']}"
                    for c in vector_chunks
                ])

            if graph_context_data["entities"]:
                graph_context_text = "Entities:\n" + "\n".join([
                    f"- {n.get('name', n['id'])} ({n.get('type', 'concept')}): {n.get('description', '')}"
                    for n in graph_context_data["entities"]
                ])
                if graph_context_data["relationships"]:
                    graph_context_text += "\n\nRelationships:\n" + "\n".join([
                        f"- {e.get('source', '')} → {e.get('target', '')} ({e.get('type', '')}): {e.get('description', '')}"
                        for e in graph_context_data["relationships"]
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
        else:
            prompt_instruction = "Please provide a comprehensive, educational response:"

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
                f"{prompt_instruction}"
            )
        else:
            user_content = question

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
