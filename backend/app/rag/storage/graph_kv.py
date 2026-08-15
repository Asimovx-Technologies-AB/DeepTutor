"""
Stage 3 — LightRAG-style JSON-KV Knowledge Graph Store
=========================================================
Replaces the NetworkX pickle-based graph_store.py.

Storage layout (per topic under LIGHTRAG_DATA_DIR):
  {topic_id}/
    entities.json    — {entity_id: {name, type, description, sources, mentions}}
    relations.json   — {relation_id: {source_entity, target_entity, type, description, sources}}
    triplets.json    — [{head, relation, tail, confidence, source_chunk_id, source_doc}]

Features:
  - Fully portable JSON format (no NetworkX, no pickle)
  - Fast BFS multi-hop entity traversal (depth 2 by default)
  - Entity deduplication by name (case-insensitive)
  - get_full_graph() returns nodes/edges dict for visualization
  - Same interface as legacy graph_store.py for backward compat
"""
from __future__ import annotations

import json
import re
import uuid
from collections import deque
from pathlib import Path
from typing import Dict, List, Optional, Any

from app.core.config import get_settings

settings = get_settings()

_ROOT = Path(settings.LIGHTRAG_DATA_DIR)


# ══════════════════════════════════════════════════════════════════════════════
# Helpers
# ══════════════════════════════════════════════════════════════════════════════
def _safe_id(name: str) -> str:
    """Convert entity name to a filesystem-safe ID."""
    return re.sub(r'[^a-z0-9_]', '_', name.lower().strip())[:80]


def _load_json(path: Path, default: Any) -> Any:
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        pass
    return default


def _save_json(path: Path, data: Any) -> None:
    try:
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as e:
        print(f"[GRAPH KV] Save error {path}: {e}")


# ══════════════════════════════════════════════════════════════════════════════
# TopicGraph — manages one topic's entities/relations/triplets
# ══════════════════════════════════════════════════════════════════════════════
class _TopicGraph:
    def __init__(self, topic_id: str):
        self.topic_id = topic_id
        self.dir = _ROOT / topic_id.replace("-", "_")
        self.dir.mkdir(parents=True, exist_ok=True)
        self._entities_path = self.dir / "entities.json"
        self._relations_path = self.dir / "relations.json"
        self._triplets_path = self.dir / "triplets.json"

        self._entities: Dict[str, Dict] = _load_json(self._entities_path, {})
        self._relations: Dict[str, Dict] = _load_json(self._relations_path, {})
        self._triplets: List[Dict] = _load_json(self._triplets_path, [])

    # ── Entities ──────────────────────────────────────────────────────────────
    def add_entities(self, entities: List[Dict]) -> None:
        changed = False
        for e in entities:
            name = str(e.get("name", "")).strip()
            if not name:
                continue
            eid = _safe_id(name)
            if eid in self._entities:
                # Merge: increment mention count
                self._entities[eid]["mentions"] = self._entities[eid].get("mentions", 1) + 1
                src = e.get("source", "")
                if src and src not in self._entities[eid].get("sources", []):
                    self._entities[eid].setdefault("sources", []).append(src)
            else:
                self._entities[eid] = {
                    "id": eid,
                    "name": name,
                    "type": e.get("type", "concept"),
                    "description": e.get("description", ""),
                    "sources": [e.get("source", "")] if e.get("source") else [],
                    "mentions": 1,
                }
            changed = True
        if changed:
            _save_json(self._entities_path, self._entities)

    # ── Relations ─────────────────────────────────────────────────────────────
    def add_relations(self, relations: List[Dict]) -> None:
        changed = False
        for r in relations:
            src_name = str(r.get("source", r.get("source_entity", ""))).strip()
            tgt_name = str(r.get("target", r.get("target_entity", ""))).strip()
            rel_type = str(r.get("type", "RELATED_TO")).strip().upper()
            if not src_name or not tgt_name:
                continue
            rid = f"{_safe_id(src_name)}___{rel_type}___{_safe_id(tgt_name)}"
            if rid not in self._relations:
                self._relations[rid] = {
                    "id": rid,
                    "source_entity": src_name,
                    "target_entity": tgt_name,
                    "type": rel_type,
                    "description": r.get("description", ""),
                    "sources": [r.get("source", "")] if r.get("source") else [],
                }
                changed = True
        if changed:
            _save_json(self._relations_path, self._relations)

    # ── Triplets ──────────────────────────────────────────────────────────────
    def add_triplets(self, triplets: List[Dict]) -> None:
        """Store GraphTriplet dicts. Deduplicates by (head, relation, tail)."""
        existing_keys = {
            f"{t['head']}||{t['relation']}||{t['tail']}"
            for t in self._triplets
        }
        changed = False
        for t in triplets:
            head = str(t.get("head", "")).strip()
            relation = str(t.get("relation", "")).strip().upper()
            tail = str(t.get("tail", "")).strip()
            if not head or not relation or not tail:
                continue
            key = f"{head}||{relation}||{tail}"
            if key not in existing_keys:
                self._triplets.append({
                    "head": head,
                    "relation": relation,
                    "tail": tail,
                    "confidence": float(t.get("confidence", 0.7)),
                    "source_chunk_id": t.get("source_chunk_id", ""),
                    "source_doc": t.get("source_doc", ""),
                })
                existing_keys.add(key)
                changed = True
        if changed:
            _save_json(self._triplets_path, self._triplets)

    # ── Entity lookup ─────────────────────────────────────────────────────────
    def get_entity(self, name: str) -> Optional[Dict]:
        return self._entities.get(_safe_id(name))

    def find_entities(self, names: List[str]) -> List[Dict]:
        found = []
        for name in names:
            e = self.get_entity(name)
            if e:
                found.append(e)
        return found

    def find_entities_in_query(self, query: str, max_entities: int = 6) -> List[str]:
        """
        Instant heuristic match of entities mentioned in user query (< 0.1ms).
        Matches n-grams (3-gram down to 1-gram) against the loaded entity index.
        """
        text_clean = re.sub(r'[^\w\s]', ' ', query.lower())
        words = text_clean.split()
        matched = []
        seen = set()
        for n in (3, 2, 1):
            for i in range(len(words) - n + 1):
                ngram = "_".join(words[i:i+n])
                if ngram in self._entities and ngram not in seen:
                    seen.add(ngram)
                    matched.append(self._entities[ngram]["name"])
                    if len(matched) >= max_entities:
                        return matched
        return matched

    # ── BFS multi-hop traversal ───────────────────────────────────────────────
    def get_entity_context(
        self,
        entity_names: List[str],
        hop_depth: int = None,
        top_entities: int = None,
        top_edges: int = None,
    ) -> Dict:
        """
        BFS traversal from seed entities, returns context dict with:
          entities:    List of entity dicts
          relations:   List of relation dicts
          triplets:    Relevant triplets
          context_text: Formatted text for LLM context injection
        """
        hop_depth = hop_depth or settings.GRAPH_HOP_DEPTH
        top_entities = top_entities or settings.GRAPH_TOP_ENTITIES
        top_edges = top_edges or settings.GRAPH_TOP_EDGES

        # Build adjacency from triplets
        adj: Dict[str, List[Dict]] = {}
        for t in self._triplets:
            adj.setdefault(t["head"].lower(), []).append(t)
            adj.setdefault(t["tail"].lower(), []).append(t)

        visited_entities: Dict[str, Dict] = {}
        visited_triplets: List[Dict] = []
        queue = deque()

        # Seed with found entities
        seeds = self.find_entities(entity_names)
        for e in seeds:
            visited_entities[e["id"]] = e
            queue.append((e["name"].lower(), 0))

        # BFS
        while queue:
            current_name, depth = queue.popleft()
            if depth >= hop_depth:
                continue
            for t in adj.get(current_name, []):
                if t not in visited_triplets:
                    visited_triplets.append(t)
                # Follow to neighbor
                neighbor = t["tail"] if t["head"].lower() == current_name else t["head"]
                nid = _safe_id(neighbor)
                if nid not in visited_entities and len(visited_entities) < top_entities:
                    ne = self.get_entity(neighbor)
                    if ne:
                        visited_entities[nid] = ne
                    else:
                        visited_entities[nid] = {"id": nid, "name": neighbor, "type": "concept", "description": ""}
                    queue.append((neighbor.lower(), depth + 1))

        entities_list = list(visited_entities.values())[:top_entities]
        triplets_list = visited_triplets[:top_edges]

        # Build matching relations from loaded relations
        seed_names_lower = {e["name"].lower() for e in entities_list}
        relevant_relations = [
            r for r in self._relations.values()
            if r["source_entity"].lower() in seed_names_lower
            or r["target_entity"].lower() in seed_names_lower
        ][:top_edges]

        # Format context text
        context_parts = []
        if entities_list:
            context_parts.append("**Knowledge Graph Entities:**")
            for e in entities_list:
                desc = e.get("description", "")
                context_parts.append(f"• {e['name']} ({e['type']})" + (f": {desc}" if desc else ""))
        if triplets_list:
            context_parts.append("\n**Knowledge Graph Relationships:**")
            for t in triplets_list:
                context_parts.append(f"• {t['head']} --[{t['relation']}]--> {t['tail']}")

        return {
            "entities": entities_list,
            "relations": relevant_relations,
            "triplets": triplets_list,
            "context_text": "\n".join(context_parts),
        }

    # ── Visualization ─────────────────────────────────────────────────────────
    def get_full_graph(self) -> Dict:
        """Return nodes/edges dict for frontend graph visualization."""
        nodes = [
            {
                "id": e["id"],
                "name": e["name"],
                "type": e.get("type", "concept"),
                "description": e.get("description", ""),
                "mentions": e.get("mentions", 1),
            }
            for e in self._entities.values()
        ]
        edges = [
            {
                "source": _safe_id(r["source_entity"]),
                "target": _safe_id(r["target_entity"]),
                "type": r["type"],
                "description": r.get("description", ""),
            }
            for r in self._relations.values()
        ]
        return {"nodes": nodes, "edges": edges}

    def get_graph_stats(self) -> Dict:
        return {
            "node_count": len(self._entities),
            "edge_count": len(self._relations),
            "triplet_count": len(self._triplets),
            "backend": "json_kv",
        }

    def delete(self) -> None:
        import shutil
        try:
            shutil.rmtree(self.dir, ignore_errors=True)
        except Exception:
            pass
        self._entities = {}
        self._relations = {}
        self._triplets = []


# ══════════════════════════════════════════════════════════════════════════════
# GraphKVStore — Public API (drop-in for legacy graph_store.py)
# ══════════════════════════════════════════════════════════════════════════════
class GraphKVStore:
    """
    LightRAG-style JSON-KV knowledge graph store.
    Drop-in replacement for the legacy NetworkX graph_store.
    """

    def __init__(self):
        _ROOT.mkdir(parents=True, exist_ok=True)
        self._topics: Dict[str, _TopicGraph] = {}

    def _topic(self, topic_id: str) -> _TopicGraph:
        if topic_id not in self._topics:
            self._topics[topic_id] = _TopicGraph(topic_id)
        return self._topics[topic_id]

    # ── Write ─────────────────────────────────────────────────────────────────
    def add_entities(self, topic_id: str, entities: List[Dict]) -> None:
        self._topic(topic_id).add_entities(entities)

    def add_relations(self, topic_id: str, relations: List[Dict]) -> None:
        self._topic(topic_id).add_relations(relations)

    def add_triplets(self, topic_id: str, triplets: List[Dict]) -> None:
        self._topic(topic_id).add_triplets(triplets)

    # ── Read ──────────────────────────────────────────────────────────────────
    def get_entity_context(
        self,
        topic_id: str,
        entity_names: List[str],
        hop_depth: int = None,
    ) -> Dict:
        return self._topic(topic_id).get_entity_context(entity_names, hop_depth)

    def get_entity_context_for_query(
        self,
        topic_id: str,
        query: str,
        hop_depth: int = None,
    ) -> Dict:
        """Instant query entity matching + BFS subgraph extraction (<1ms)."""
        topic = self._topic(topic_id)
        matched_names = topic.find_entities_in_query(query)
        if not matched_names:
            return {"entities": [], "relations": [], "triplets": [], "context_text": ""}
        return topic.get_entity_context(matched_names, hop_depth)

    def get_full_graph(self, topic_id: str) -> Dict:
        return self._topic(topic_id).get_full_graph()

    def get_graph_stats(self, topic_id: str) -> Dict:
        return self._topic(topic_id).get_graph_stats()

    # ── Legacy interface (backward compat) ────────────────────────────────────
    def add_node(self, topic_id: str, entity: Dict) -> None:
        """Legacy: add single entity node."""
        self.add_entities(topic_id, [entity])

    def add_edge(self, topic_id: str, source: str, target: str, rel_type: str = "RELATED_TO", **kwargs) -> None:
        """Legacy: add single relation edge."""
        self.add_relations(topic_id, [{"source": source, "target": target, "type": rel_type, **kwargs}])

    def get_neighbors(self, topic_id: str, entity_name: str, depth: int = 1) -> Dict:
        """Legacy: get neighbor context for entity."""
        return self.get_entity_context(topic_id, [entity_name], hop_depth=depth)

    # ── Delete ────────────────────────────────────────────────────────────────
    def delete_graph(self, topic_id: str) -> None:
        t = self._topics.pop(topic_id, None)
        if t:
            t.delete()
        else:
            _TopicGraph(topic_id).delete()

    def reset(self) -> None:
        for t in list(self._topics.values()):
            t.delete()
        self._topics.clear()
        try:
            import shutil
            shutil.rmtree(_ROOT, ignore_errors=True)
            _ROOT.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass
