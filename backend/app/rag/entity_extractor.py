"""
Stage 2 — Graph Triplet & Entity Extractor
============================================
Extracts structured knowledge graph triplets from text chunks using LLM.

Output per chunk:
  entities    : [{name, type, description, source}]
  relations   : [{source_entity, target_entity, type, description}]
  triplets    : [{head, relation, tail, confidence, source_chunk_id}]

GraphTriplet (head, relation, tail) is the core LightRAG-style data unit
stored in the JSON-KV knowledge graph (storage/graph_kv.py).

Supports:
  - Ollama (local, default)
  - Any LLM via the OllamaClient interface
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, asdict
from typing import List, Dict, Tuple, Optional
from app.rag.ollama_client import ollama

# ── GraphTriplet Dataclass ────────────────────────────────────────────────────

@dataclass
class GraphTriplet:
    """
    Core knowledge graph unit: (head entity) -[relation]→ (tail entity)
    Stored in LightRAG-style JSON-KV graph store.
    """
    head: str              # Subject entity name
    relation: str          # Predicate / relationship type
    tail: str              # Object entity name
    confidence: float      # Extraction confidence [0.0, 1.0]
    source_chunk_id: str   # Chunk ID this triplet was extracted from
    source_doc: str = ""   # Document filename

    def to_dict(self) -> Dict:
        return asdict(self)


# ── Extraction Prompts ────────────────────────────────────────────────────────

TRIPLET_EXTRACTION_PROMPT = """You are a precise knowledge graph extraction expert.
Extract technical concepts, their relationships, and graph triplets from the given text.

Return ONLY valid JSON in this exact format:
{{
  "entities": [
    {{"name": "Entity Name", "type": "concept|algorithm|method|formula|law|theorem|system", "description": "brief description"}}
  ],
  "relations": [
    {{"source": "Entity A", "target": "Entity B", "type": "relationship_type", "description": "how they relate"}}
  ],
  "triplets": [
    {{"head": "Entity A", "relation": "USES", "tail": "Entity B", "confidence": 0.9}},
    {{"head": "Method X", "relation": "IMPROVES", "tail": "Accuracy", "confidence": 0.85}}
  ]
}}

Strict Rules:
- Extract 3–8 important TECHNICAL concepts per chunk
- DO NOT extract author names, countries, cities, or page metadata headers
- Entity names: concise (1–4 words), fix obvious typos
- Relations: uppercase verbs (USES, IMPROVES, REQUIRES, DEFINES, EXTENDS, APPLIES_TO, PART_OF, COMPARED_TO)
- Confidence: float 0.0–1.0 based on how clearly the relationship is stated
- If no clear technical entities exist, return {{"entities": [], "relations": [], "triplets": []}}

TEXT:
{text}

JSON:"""


QUERY_ENTITY_PROMPT = """Extract the key concepts and entities from this question.
Return ONLY a JSON array of strings.

Question: {query}

Examples:
- "What is Newton's second law?" → ["Newton's second law", "force", "acceleration", "mass"]
- "How does photosynthesis work?" → ["photosynthesis", "chloroplast", "glucose", "light energy"]

JSON array:"""


# ── Helpers ───────────────────────────────────────────────────────────────────

def _extract_json(text: str) -> dict:
    """Robustly extract JSON dict from LLM response (handles markdown code blocks)."""
    text = text.strip()
    # Strip ```json ... ``` wrapper
    m = re.search(r'```(?:json)?\s*([\s\S]+?)\s*```', text)
    if m:
        text = m.group(1)
    # Find first {...} block
    m = re.search(r'\{[\s\S]*\}', text)
    if m:
        try:
            return json.loads(m.group())
        except json.JSONDecodeError:
            pass
    # Direct parse
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {}


# ── Public API ────────────────────────────────────────────────────────────────

async def extract_graph_triplets(
    text: str,
    source_doc: str = "",
    chunk_id: str = "",
    confidence_threshold: float = 0.5,
) -> Tuple[List[Dict], List[Dict], List[GraphTriplet]]:
    """
    Extract entities, relations, and graph triplets from a text chunk.

    Args:
        text:                 Chunk text to process
        source_doc:           Source document filename for metadata
        chunk_id:             Unique chunk ID for triplet provenance
        confidence_threshold: Minimum triplet confidence to include

    Returns:
        (entities, relations, triplets)
        - entities:  List[{name, type, description, source}]
        - relations: List[{source, target, type, description}]
        - triplets:  List[GraphTriplet]
    """
    prompt = TRIPLET_EXTRACTION_PROMPT.format(text=text[:2500])

    try:
        messages = [
            {"role": "system", "content": "You are a precise knowledge extraction assistant. Always respond with valid JSON only."},
            {"role": "user", "content": prompt},
        ]
        response = await ollama.chat(messages, temperature=0.1)
        data = _extract_json(response)

        entities = data.get("entities", [])
        relations = data.get("relations", [])
        raw_triplets = data.get("triplets", [])

        # Annotate source metadata
        for e in entities:
            e["source"] = source_doc
        for r in relations:
            r["source"] = source_doc

        # Build typed GraphTriplet objects, filtering by confidence
        triplets: List[GraphTriplet] = []
        for t in raw_triplets:
            head = str(t.get("head", "")).strip()
            relation = str(t.get("relation", "")).strip().upper()
            tail = str(t.get("tail", "")).strip()
            confidence = float(t.get("confidence", 0.7))

            if not head or not relation or not tail:
                continue
            if confidence < confidence_threshold:
                continue

            triplets.append(GraphTriplet(
                head=head,
                relation=relation,
                tail=tail,
                confidence=confidence,
                source_chunk_id=chunk_id,
                source_doc=source_doc,
            ))

        return entities, relations, triplets

    except Exception as e:
        print(f"[TRIPLET EXTRACT] Error: {e}")
        return [], [], []


async def extract_entities_and_relationships(
    text: str,
    source_info: str = "",
) -> Tuple[List[Dict], List[Dict]]:
    """
    Legacy interface: extract entities and relationships only (no triplets).
    Kept for backward compatibility with graph_rag.py callers.
    """
    entities, relations, _ = await extract_graph_triplets(
        text, source_doc=source_info
    )
    return entities, relations


def extract_query_entities(query: str) -> List[str]:
    """
    Extract key concept names and candidate entities from a user query instantly (< 0.1ms).
    Uses fast regex and n-gram extraction to avoid adding multi-second LLM latency.
    """
    # 1. Capitalized multi-word named entities: e.g. "Support Vector Machines"
    named_entities = re.findall(r'\b[A-Z][a-z0-9]+(?:\s+[A-Z][a-z0-9]+)*\b', query)
    
    # 2. Extract technical terms / key nouns
    stopwords = {
        "what", "is", "the", "a", "an", "how", "does", "why", "when", "where",
        "which", "who", "whom", "this", "that", "these", "those", "are", "was",
        "were", "be", "been", "being", "have", "has", "had", "do", "did", "can",
        "could", "should", "would", "may", "might", "must", "explain", "tell",
        "me", "about", "describe", "define", "give", "and", "or", "in", "on", "at",
        "to", "for", "with", "from", "by", "of", "as", "into", "through", "page",
        "please", "help", "find", "show", "summarize", "detail", "details"
    }
    
    words = [w for w in re.findall(r'\b[a-zA-Z0-9_\-]{3,}\b', query) if w.lower() not in stopwords]
    
    candidates = []
    for ne in named_entities:
        if ne.lower() not in stopwords and ne not in candidates:
            candidates.append(ne)
            
    for w in words:
        if w not in candidates and w.lower() not in [c.lower() for c in candidates]:
            candidates.append(w)
            
    return candidates[:6]
