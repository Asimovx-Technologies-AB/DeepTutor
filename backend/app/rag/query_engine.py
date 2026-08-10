"""
Advanced Query Engine — Industry-Level RAG Pipeline.

Components:
  QueryExpander          : Generates N alternative phrasings of a query via LLM.
  HyDEEngine             : Hypothetical Document Embedding — generate a hypothetical
                           answer first, embed it, search with that richer vector.
  ContextualCompressor   : Trims retrieved chunks to only the sentences most relevant
                           to the question (reduces noise sent to LLM).
  ConfidenceScorer       : Estimates answer confidence from retrieval signal strengths.
  GracefulOutOfScopeHandler: Detects when query has zero relevant context and
                             returns a clear "not in document" signal.
"""
import asyncio
import json
import re
from typing import List, Dict, Optional, Tuple

from app.core.config import get_settings
from app.rag.ollama_client import ollama

settings = get_settings()


# ── helpers ────────────────────────────────────────────────────────────────────
def _extract_json_list(text: str) -> List[str]:
    """Extract a JSON array of strings from LLM response, robust to markdown."""
    # Try direct parse
    try:
        return json.loads(text.strip())
    except Exception:
        pass
    # Extract [...] block
    match = re.search(r'\[.*?\]', text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except Exception:
            pass
    # Fallback: extract quoted strings
    return re.findall(r'"([^"]{5,})"', text)


def _tokenize_simple(text: str) -> List[str]:
    return [t.lower() for t in re.findall(r'\b\w+\b', text) if len(t) > 2]


# ══════════════════════════════════════════════════════════════════════════════
# QueryExpander
# ══════════════════════════════════════════════════════════════════════════════
class QueryExpander:
    """
    Generates multiple alternative phrasings of a user query.
    Merging results from all variants via deduplication improves recall
    for queries with domain-specific synonyms.
    """

    EXPAND_PROMPT = """You are an expert at reformulating search queries to improve document retrieval.
Given the user's question, generate {n} alternative phrasings that capture the same information need
but use different terminology, synonyms, or angles.

User Question: {query}

Return ONLY a JSON array of {n} strings. No explanation. Example format:
["alternative 1", "alternative 2", "alternative 3"]

JSON Array:"""

    def __init__(self, n_variants: int = 3):
        self.n_variants = n_variants

    async def expand(self, query: str) -> List[str]:
        """Returns [original_query] + [n_variants alternative phrasings]."""
        if not settings.ENABLE_QUERY_EXPANSION:
            return [query]

        prompt = self.EXPAND_PROMPT.format(n=self.n_variants, query=query)
        try:
            response = await ollama.chat(
                [{"role": "user", "content": prompt}],
                temperature=0.4,  # slight creativity for diverse phrasings
            )
            variants = _extract_json_list(response)
            # Filter: keep non-empty strings, max self.n_variants
            variants = [v.strip() for v in variants if isinstance(v, str) and len(v.strip()) > 5]
            variants = variants[:self.n_variants]
        except Exception:
            variants = []

        # Always include original first, then variants
        all_queries = [query] + [v for v in variants if v.lower() != query.lower()]
        return all_queries[:self.n_variants + 1]


# ══════════════════════════════════════════════════════════════════════════════
# HyDEEngine
# ══════════════════════════════════════════════════════════════════════════════
class HyDEEngine:
    """
    Hypothetical Document Embedding (Gao et al., 2022).
    
    Instead of embedding the raw query (short, question-form),
    we first generate a hypothetical passage that would answer the question,
    then embed THAT passage for retrieval. This dramatically improves precision
    because the embedding space is closer to real document passages.
    
    The actual answer is NOT used — only the embedding from it.
    """

    HYDE_PROMPT = """You are an expert academic author. Write a short, dense, informative passage
(3-5 sentences) that would directly answer the following question. 
Write it as if it is an excerpt from a high-quality textbook or research paper.
Do NOT say "I don't know" — write your best hypothetical answer.

Question: {query}

Hypothetical passage:"""

    async def generate_hypothetical_document(self, query: str) -> str:
        """Generate a hypothetical passage that would answer the query."""
        if not settings.ENABLE_HYDE:
            return query  # fallback to raw query

        prompt = self.HYDE_PROMPT.format(query=query)
        try:
            response = await ollama.chat(
                [{"role": "user", "content": prompt}],
                temperature=0.2,
            )
            return response.strip()
        except Exception:
            return query  # fallback to raw query on error


# ══════════════════════════════════════════════════════════════════════════════
# ContextualCompressor
# ══════════════════════════════════════════════════════════════════════════════
class ContextualCompressor:
    """
    Extracts only the sentences from retrieved chunks that are relevant
    to the question, discarding irrelevant filler.
    
    Two modes:
    - "llm"   : Uses LLM to extract relevant sentences (accurate, adds ~300ms)
    - "keyword": Fast keyword-overlap extraction (zero LLM, ~1ms)
    
    Default mode: "keyword" (can be overridden per call)
    """

    COMPRESS_PROMPT = """Extract ONLY the sentences from the passage below that are directly relevant 
to answering the question. Return them verbatim, joined with a space. 
If the passage has no relevant content, return "<IRRELEVANT>".

Question: {query}

Passage:
{passage}

Relevant sentences:"""

    async def compress(
        self,
        query: str,
        chunks: List[Dict],
        mode: str = "keyword",
    ) -> List[Dict]:
        """
        Returns chunks with text replaced by only the relevant sentences.
        Chunks with no relevant content are removed.
        """
        if not settings.ENABLE_CONTEXTUAL_COMPRESSION:
            return chunks

        if mode == "llm":
            return await self._compress_llm(query, chunks)
        else:
            return self._compress_keyword(query, chunks)

    def _compress_keyword(self, query: str, chunks: List[Dict]) -> List[Dict]:
        """
        Fast keyword-overlap sentence filtering.
        Keeps sentences that share at least 2 content tokens with the query.
        """
        query_tokens = set(_tokenize_simple(query))
        # Remove very common words from query tokens
        stopwords = {"what", "how", "why", "when", "where", "who", "does", "are",
                     "the", "and", "for", "with", "this", "that", "from", "explain"}
        query_tokens -= stopwords

        if len(query_tokens) < 2:
            return chunks  # query too short to filter meaningfully

        compressed = []
        for chunk in chunks:
            text = chunk["text"]
            sentences = re.split(r'(?<=[.!?])\s+', text)
            relevant = []
            for sent in sentences:
                sent_tokens = set(_tokenize_simple(sent))
                overlap = len(query_tokens & sent_tokens)
                if overlap >= 1:  # at least 1 content token overlap
                    relevant.append(sent)

            if relevant:
                new_chunk = dict(chunk)
                compressed_text = " ".join(relevant)
                # Keep at least 60% of original or skip
                if len(compressed_text) >= max(100, len(text) * 0.15):
                    new_chunk["text"] = compressed_text
                    new_chunk["metadata"] = dict(chunk.get("metadata", {}))
                    new_chunk["metadata"]["compressed"] = True
                    new_chunk["metadata"]["original_chars"] = len(text)
                    new_chunk["metadata"]["compressed_chars"] = len(compressed_text)
                    compressed.append(new_chunk)
                else:
                    # Too little survived — keep original
                    compressed.append(chunk)
            # If zero sentences matched, keep the chunk anyway (may still be useful)
            else:
                compressed.append(chunk)

        return compressed

    async def _compress_llm(self, query: str, chunks: List[Dict]) -> List[Dict]:
        """LLM-based sentence extraction (accurate but slower)."""
        semaphore = asyncio.Semaphore(2)  # Limit concurrent LLM calls

        async def _compress_one(chunk: Dict) -> Optional[Dict]:
            async with semaphore:
                prompt = self.COMPRESS_PROMPT.format(
                    query=query,
                    passage=chunk["text"][:1200],
                )
                try:
                    response = await ollama.chat(
                        [{"role": "user", "content": prompt}],
                        temperature=0.0,
                    )
                    compressed_text = response.strip()
                    if "<IRRELEVANT>" in compressed_text or len(compressed_text) < 20:
                        return None  # Mark for removal
                    new_chunk = dict(chunk)
                    new_chunk["text"] = compressed_text
                    new_chunk["metadata"] = dict(chunk.get("metadata", {}))
                    new_chunk["metadata"]["compressed"] = True
                    return new_chunk
                except Exception:
                    return chunk  # Keep original on error

        results = await asyncio.gather(*[_compress_one(c) for c in chunks])
        return [r for r in results if r is not None]


# ══════════════════════════════════════════════════════════════════════════════
# ConfidenceScorer
# ══════════════════════════════════════════════════════════════════════════════
class ConfidenceScorer:
    """
    Estimates how confident the RAG system is in its retrieved context.
    Uses retrieval signal strength (chunk scores) + graph coverage.
    Returns a float [0.0, 1.0] and a human-readable label.
    """

    THRESHOLDS = {
        "high":   0.65,
        "medium": 0.40,
        "low":    0.20,
    }

    def score(
        self,
        chunks: List[Dict],
        graph_entities: List[Dict],
        query: str,
    ) -> Tuple[float, str]:
        """
        Returns (confidence_score, label).
        label: "high" | "medium" | "low" | "out_of_scope"
        """
        if not chunks:
            return 0.0, "out_of_scope"

        # 1. Average retrieval score (cosine similarity)
        scores = [c.get("rerank_score", c.get("score", 0.0)) for c in chunks]
        avg_score = sum(scores) / len(scores) if scores else 0.0
        max_score = max(scores) if scores else 0.0

        # 2. Graph coverage bonus
        graph_bonus = min(0.1, len(graph_entities) * 0.01)

        # 3. Keyword coverage in retrieved text
        query_tokens = set(_tokenize_simple(query))
        combined_text = " ".join(c["text"] for c in chunks).lower()
        doc_tokens = set(_tokenize_simple(combined_text))
        kw_coverage = len(query_tokens & doc_tokens) / max(len(query_tokens), 1)

        # Combined confidence
        confidence = (0.5 * max_score + 0.3 * avg_score + 0.1 * kw_coverage + graph_bonus)
        confidence = round(min(1.0, confidence), 4)

        if confidence >= self.THRESHOLDS["high"]:
            label = "high"
        elif confidence >= self.THRESHOLDS["medium"]:
            label = "medium"
        elif confidence >= self.THRESHOLDS["low"]:
            label = "low"
        else:
            label = "out_of_scope"

        return confidence, label


# ══════════════════════════════════════════════════════════════════════════════
# GracefulOutOfScopeHandler
# ══════════════════════════════════════════════════════════════════════════════
class GracefulOutOfScopeHandler:
    """
    Detects when a query has no relevant content in the document
    and returns a clear explanation instead of hallucinating.
    """

    OUT_OF_SCOPE_RESPONSE = (
        "I couldn't find information about **{topic}** in the uploaded document. "
        "This topic may not be covered in your current study material.\n\n"
        "💡 **Suggestions:**\n"
        "- Try rephrasing your question using terms from the document\n"
        "- Check if this topic is covered in a different section\n"
        "- Upload a document that covers this topic\n\n"
        "I can answer from my general knowledge if you'd like — just ask!"
    )

    def is_out_of_scope(self, confidence: float, label: str) -> bool:
        return label == "out_of_scope"

    def format_response(self, query: str) -> str:
        # Extract the key topic from the query
        topic = query.strip().rstrip("?").rstrip(".")
        if len(topic) > 60:
            topic = topic[:60] + "..."
        return self.OUT_OF_SCOPE_RESPONSE.format(topic=topic)


# ── Singletons ─────────────────────────────────────────────────────────────────
query_expander        = QueryExpander()
hyde_engine           = HyDEEngine()
contextual_compressor = ContextualCompressor()
confidence_scorer     = ConfidenceScorer()
oos_handler           = GracefulOutOfScopeHandler()
