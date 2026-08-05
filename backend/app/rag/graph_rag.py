"""
GraphRAG Pipeline — the core orchestrator.

Index phase:
  document → chunks → embeddings (ChromaDB) + entities/relationships (NetworkX)

Query phase:
  question → vector search + graph search → context assembly → Ollama stream
"""
import json
import re
from typing import List, Dict, AsyncGenerator, Optional
from app.rag.ollama_client import ollama
from app.rag.document_processor import process_document
from app.rag.entity_extractor import extract_entities_and_relationships, extract_query_entities
from app.rag.graph_store import graph_store
from app.rag.vector_store import vector_store
from app.core.config import get_settings

settings = get_settings()

# ─── System Prompt ─────────────────────────────────────────────────────────────
SYSTEM_PROMPT = """You are DeepTutor, an expert AI tutor powered by local AI.
You have access to a knowledge graph and document context to provide accurate, detailed explanations.

Guidelines:
- Be educational, clear, and encouraging
- Use the provided context to answer accurately
- When explaining concepts, break them down step by step
- Strict Rule for Page Numbers:
  * Pay strict attention to the source page numbers [doc p.X] in the Document Context.
  * If the student asks about specific page numbers (e.g., page 94 and 95), answer ONLY using context from those requested page numbers.
  * If the requested page numbers are NOT present in the Document Context or marked as missing, explicitly state: "The requested page number(s) were not found in the uploaded document context."
  * NEVER hallucinate or claim that content from other pages comes from the requested page numbers.
- If you reference information from the context, mention the source and page number
- Use markdown formatting for clarity (headers, bullets, code blocks, formulas)
- If context doesn't cover the question, use your general knowledge but indicate this clearly
"""

CONVERSED_PROMPT = SYSTEM_PROMPT


def extract_requested_pages(text: str) -> List[int]:
    """
    Extract page numbers requested in user question.
    Handles:
    - 'page number 94 and 95' -> [94, 95]
    - 'pages 94-96' or 'pages 94 to 96' -> [94, 95, 96]
    - 'page 94' -> [94]
    - 'p. 94', 'p94' -> [94]
    """
    pages = set()
    text_lower = text.lower()

    # Match ranges: pages 94-96, pages 94 to 96
    range_pattern = r'(?:pages?|p\.?)\s*(?:numbers?|no\.?|nums?)?\s*(\d+)\s*(?:-|to)\s*(\d+)'
    for match in re.finditer(range_pattern, text_lower):
        start, end = int(match.group(1)), int(match.group(2))
        if start <= end and (end - start) <= 50:
            pages.update(range(start, end + 1))

    # Match lists: page number 94 and 95, pages 94, 95, 96
    list_pattern = r'(?:pages?|p\.?)\s*(?:numbers?|no\.?|nums?)?\s*(\d+(?:\s*(?:,|and|&)\s*\d+)+)'
    for match in re.finditer(list_pattern, text_lower):
        nums = re.findall(r'\d+', match.group(1))
        pages.update([int(n) for n in nums])

    # Match single page: page 94, p.94, page number 94
    single_pattern = r'(?:pages?|p\.?)\s*(?:numbers?|no\.?|nums?)?\s*(\d+)'
    for match in re.finditer(single_pattern, text_lower):
        pages.add(int(match.group(1)))

    return sorted(list(pages))


CONTEXT_TEMPLATE = """## Knowledge Graph Context
Relevant entities and relationships retrieved from the knowledge graph:
{graph_context}

## Document Context  
Relevant passages from uploaded documents:
{vector_context}

## Conversation History
{history}

## Student Question
{question}

Please provide a comprehensive, educational response:"""


class GraphRAGPipeline:
    """Main GraphRAG pipeline. One instance shared across requests."""

    # ── Indexing ───────────────────────────────────────────────────────────────
    async def index_document(
        self,
        topic_id: str,
        file_path: str,
        progress_callback=None,
    ) -> Dict:
        """
        Full indexing pipeline:
        1. Parse document into chunks
        2. Embed chunks → ChromaDB
        3. Extract entities/relationships → graph_store
        Returns stats dict.
        """
        # Step 1: Parse
        if progress_callback:
            await progress_callback("parsing", 0)
        chunks = process_document(file_path)
        if not chunks:
            raise ValueError("No text could be extracted from the document. Please verify that the PDF has selectable text and is not empty or scanned/image-only.")
        total = len(chunks)

        # Step 2: Embed + store in vector DB
        if progress_callback:
            await progress_callback("embedding", 10)

        embeddings = await ollama.embed_batch([chunk["text"] for chunk in chunks])
        if progress_callback:
            await progress_callback("embedding", 50)

        vector_store.add_chunks(topic_id, chunks, embeddings)

        # Step 3: Entity extraction (process every 3rd chunk to save LLM calls)
        if progress_callback:
            await progress_callback("extracting_entities", 50)

        import asyncio
        all_entities = []
        all_relationships = []
        sample_chunks = chunks[::3]  # Every 3rd chunk
        
        semaphore = asyncio.Semaphore(3)  # Run 3 extraction queries concurrently
        
        async def _sem_extract(chunk: dict, index: int):
            async with semaphore:
                source = chunk["metadata"].get("source", "")
                page = chunk["metadata"].get("page", "")
                source_info = f"{source} p.{page}"
                entities, relationships = await extract_entities_and_relationships(
                    chunk["text"], source_info
                )
                if progress_callback:
                    # Update progress dynamically
                    pct = 50 + int((index / len(sample_chunks)) * 45)
                    await progress_callback("extracting_entities", pct)
                return entities, relationships

        tasks = [_sem_extract(chunk, idx) for idx, chunk in enumerate(sample_chunks)]
        results = await asyncio.gather(*tasks)
        
        for entities, relationships in results:
            all_entities.extend(entities)
            all_relationships.extend(relationships)

        # Step 4: Update graph
        graph_store.add_entities(topic_id, all_entities)
        graph_store.add_relationships(topic_id, all_relationships)

        stats = graph_store.get_graph_stats(topic_id)
        if progress_callback:
            await progress_callback("done", 100)

        return {
            "chunks_indexed": total,
            "entities_extracted": len(all_entities),
            "relationships_extracted": len(all_relationships),
            "graph_nodes": stats["node_count"],
            "graph_edges": stats["edge_count"],
        }

    # ── Querying ───────────────────────────────────────────────────────────────
    async def query_stream(
        self,
        topic_id: Optional[str],
        question: str,
        session_messages: List[Dict],
    ) -> AsyncGenerator[str, None]:
        """
        Full GraphRAG query with SSE streaming.

        Yields JSON-encoded events:
          {"type": "sources", "data": [...]}
          {"type": "graph_context", "data": {...}}
          {"type": "token", "data": "..."}
          {"type": "done"}
        """
        vector_chunks = []
        graph_context_data = {"entities": [], "relationships": []}
        graph_context_text = ""
        vector_context_text = ""

        # topic_id is already namespaced by the caller as {user_id}_{topic}
        # so we use it directly — no fallback needed here
        effective_topic_id = topic_id or ""

        # ── Step 1: Retrieval (only if topic has indexed data) ─────────────────
        if effective_topic_id and vector_store.count(effective_topic_id) > 0:
            requested_pages = extract_requested_pages(question)
            page_chunks = []
            if requested_pages:
                page_chunks = vector_store.get_chunks_by_pages(effective_topic_id, requested_pages)

            # Vector search
            query_emb = await ollama.embed(question)
            vector_chunks = vector_store.search(
                effective_topic_id, query_emb, top_k=settings.TOP_K_CHUNKS
            )

            if requested_pages:
                if page_chunks:
                    # Combine exact page_chunks first, then vector_chunks without duplicates
                    seen_texts = set()
                    combined = []
                    for c in page_chunks + vector_chunks:
                        t = c["text"]
                        if t not in seen_texts:
                            seen_texts.add(t)
                            combined.append(c)
                    vector_chunks = combined
                else:
                    # System notice if requested pages do not exist in document
                    missing_str = ", ".join([str(p) for p in requested_pages])
                    vector_chunks.insert(0, {
                        "text": f"[SYSTEM NOTICE: The student explicitly asked about page(s) {missing_str}, but no content for page(s) {missing_str} was found in the indexed document.]",
                        "metadata": {"source": "System", "page": f"Missing ({missing_str})"},
                        "score": 1.0,
                    })

            # Graph search
            query_entities = await extract_query_entities(question)
            all_graph_nodes = []
            all_graph_edges = []

            for entity_term in query_entities[:3]:  # Limit to top 3 entities
                relevant = graph_store.find_relevant_entities(effective_topic_id, [entity_term])
                for ent in relevant[:2]:
                    subgraph = graph_store.search_neighbors(
                        effective_topic_id, ent["id"], hops=settings.GRAPH_HOP_DEPTH
                    )
                    all_graph_nodes.extend(subgraph["nodes"])
                    all_graph_edges.extend(subgraph["edges"])


            # Deduplicate graph nodes
            seen_nodes = set()
            unique_nodes = []
            for n in all_graph_nodes:
                if n["id"] not in seen_nodes:
                    seen_nodes.add(n["id"])
                    unique_nodes.append(n)

            graph_context_data = {"entities": unique_nodes[:15], "relationships": all_graph_edges[:20]}

            # Build text representations
            if vector_chunks:
                vector_context_text = "\n\n".join([
                    f"[{c['metadata'].get('source','doc')} p.{c['metadata'].get('page','')}] "
                    f"(relevance: {c['score']:.0%})\n{c['text']}"
                    for c in vector_chunks
                ])

            if unique_nodes:
                graph_context_text = "Entities:\n" + "\n".join([
                    f"- {n.get('name', n['id'])} ({n.get('type','concept')}): {n.get('description','')}"
                    for n in unique_nodes[:8]
                ])
                if all_graph_edges:
                    graph_context_text += "\n\nRelationships:\n" + "\n".join([
                        f"- {e.get('source','')} → {e.get('target','')} ({e.get('type','')}): {e.get('description','')}"
                        for e in all_graph_edges[:8]
                    ])

        # ── Step 2: Emit sources + graph context ───────────────────────────────
        if vector_chunks:
            sources_payload = [
                {
                    "doc": c["metadata"].get("source", "document"),
                    "page": c["metadata"].get("page", 1),
                    "score": c["score"],
                    "text": c["text"][:300] + "..." if len(c["text"]) > 300 else c["text"],
                }
                for c in vector_chunks
            ]
            yield f"data: {json.dumps({'type': 'sources', 'data': sources_payload})}\n\n"

        if graph_context_data["entities"]:
            yield f"data: {json.dumps({'type': 'graph_context', 'data': graph_context_data})}\n\n"

        # ── Step 3: Build messages for Ollama ──────────────────────────────────
        history_text = ""
        for msg in session_messages[-6:]:  # Last 6 messages for context window
            role_label = "Student" if msg["role"] == "user" else "Tutor"
            history_text += f"{role_label}: {msg['content'][:500]}\n"

        # Use context if available, else just answer from knowledge
        if graph_context_text or vector_context_text:
            user_content = CONTEXT_TEMPLATE.format(
                graph_context=graph_context_text or "No graph entities found for this query.",
                vector_context=vector_context_text or "No document passages found for this query.",
                history=history_text or "No prior conversation.",
                question=question,
            )
        else:
            user_content = question

        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ]

        # ── Step 4: Stream tokens ──────────────────────────────────────────────
        full_response = ""
        async for token in ollama.stream(messages):
            full_response += token
            yield f"data: {json.dumps({'type': 'token', 'data': token})}\n\n"

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
            except Exception:
                pass

        return {
            "content": full_text,
            "sources": sources,
            "graph_context": graph_data,
        }


# Singleton pipeline
graph_rag = GraphRAGPipeline()
