"""
Entity & Relationship extractor using local Ollama LLM.
Extracts structured knowledge from text chunks for the knowledge graph.
"""
import json
import re
from typing import List, Dict, Tuple
from app.rag.ollama_client import ollama

EXTRACTION_PROMPT = """You are a knowledge graph extraction expert. Extract entities and relationships from the given text.

Return ONLY valid JSON in this exact format:
{{
  "entities": [
    {{"name": "Entity Name", "type": "concept|person|place|event|formula|law|theorem", "description": "brief description"}}
  ],
  "relationships": [
    {{"source": "Entity A", "target": "Entity B", "type": "relationship_type", "description": "how they relate"}}
  ]
}}

Rules:
- Extract 3-8 important entities per chunk
- Extract meaningful relationships between entities
- Entity names should be concise (1-4 words)
- Relationship types: "is_a", "part_of", "causes", "defines", "requires", "opposes", "related_to", "formula_for", "example_of"
- If no clear entities exist, return {{"entities": [], "relationships": []}}

TEXT:
{text}

JSON:"""


async def extract_entities_and_relationships(
    text: str,
    source_info: str = "",
) -> Tuple[List[Dict], List[Dict]]:
    """
    Extract entities and relationships from a text chunk using Ollama.
    Returns (entities, relationships).
    """
    prompt = EXTRACTION_PROMPT.format(text=text[:2000])  # cap to avoid context overflow

    try:
        messages = [
            {"role": "system", "content": "You are a precise knowledge extraction assistant. Always respond with valid JSON only."},
            {"role": "user", "content": prompt},
        ]
        response = await ollama.chat(messages, temperature=0.1)

        # Extract JSON from response (handle markdown code blocks)
        json_str = response.strip()
        json_match = re.search(r'\{.*\}', json_str, re.DOTALL)
        if json_match:
            json_str = json_match.group()

        data = json.loads(json_str)
        entities = data.get("entities", [])
        relationships = data.get("relationships", [])

        # Add source metadata
        for e in entities:
            e["source"] = source_info
        for r in relationships:
            r["source"] = source_info

        return entities, relationships

    except (json.JSONDecodeError, Exception) as e:
        # Fallback: return empty on parse failure
        return [], []


async def extract_query_entities(query: str) -> List[str]:
    """
    Extract key entity names from a user query for graph lookup.
    Returns list of entity name strings.
    """
    prompt = f"""Extract the key concepts and entities from this question. Return ONLY a JSON array of strings.

Question: {query}

Examples:
- "What is Newton's second law?" → ["Newton's second law", "force", "acceleration", "mass"]
- "How does photosynthesis work?" → ["photosynthesis", "chloroplast", "glucose", "light"]

JSON array:"""

    try:
        messages = [{"role": "user", "content": prompt}]
        response = await ollama.chat(messages, temperature=0.0)

        json_str = response.strip()
        arr_match = re.search(r'\[.*?\]', json_str, re.DOTALL)
        if arr_match:
            return json.loads(arr_match.group())
        return []
    except Exception:
        # Simple keyword fallback
        import re as _re
        words = _re.findall(r'\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\b', query)
        return words[:5]
