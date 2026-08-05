"""
NetworkX-based Knowledge Graph Store.
Persists graph as JSON files per topic.
"""
import json
import os
from pathlib import Path
from typing import List, Dict, Set, Optional, Tuple
import networkx as nx
from app.core.config import get_settings

settings = get_settings()


class GraphStore:
    """
    Knowledge graph backed by NetworkX DiGraph.
    One graph per topic_id, persisted to disk.
    """

    def __init__(self):
        self._graphs: Dict[str, nx.DiGraph] = {}
        self.data_dir = Path(settings.GRAPH_DATA_DIR)
        self.data_dir.mkdir(parents=True, exist_ok=True)

    def _graph_path(self, topic_id: str) -> Path:
        return self.data_dir / f"{topic_id}.json"

    def _load_graph(self, topic_id: str) -> nx.DiGraph:
        """Load graph from disk or create new."""
        if topic_id in self._graphs:
            return self._graphs[topic_id]

        path = self._graph_path(topic_id)
        G = nx.DiGraph()

        if path.exists():
            try:
                data = json.loads(path.read_text())
                for node in data.get("nodes", []):
                    G.add_node(node["id"], **node.get("attrs", {}))
                for edge in data.get("edges", []):
                    G.add_edge(edge["source"], edge["target"], **edge.get("attrs", {}))
            except Exception:
                pass  # Start fresh on corruption

        self._graphs[topic_id] = G
        return G

    def _save_graph(self, topic_id: str) -> None:
        """Persist graph to disk."""
        G = self._graphs.get(topic_id)
        if G is None:
            return
        path = self._graph_path(topic_id)
        data = {
            "nodes": [{"id": n, "attrs": G.nodes[n]} for n in G.nodes],
            "edges": [
                {"source": u, "target": v, "attrs": G.edges[u, v]}
                for u, v in G.edges
            ],
        }
        path.write_text(json.dumps(data, indent=2))

    def add_entities(self, topic_id: str, entities: List[Dict]) -> None:
        """Add entity nodes to the graph."""
        G = self._load_graph(topic_id)
        for entity in entities:
            name = entity.get("name", "").strip()
            if not name:
                continue
            node_id = name.lower()
            if G.has_node(node_id):
                # Merge: keep existing, update if richer
                existing = G.nodes[node_id]
                if not existing.get("description") and entity.get("description"):
                    G.nodes[node_id]["description"] = entity["description"]
            else:
                G.add_node(
                    node_id,
                    name=name,
                    type=entity.get("type", "concept"),
                    description=entity.get("description", ""),
                    source=entity.get("source", ""),
                )
        self._save_graph(topic_id)

    def add_relationships(self, topic_id: str, relationships: List[Dict]) -> None:
        """Add relationship edges to the graph."""
        G = self._load_graph(topic_id)
        for rel in relationships:
            src = rel.get("source", "").lower().strip()
            tgt = rel.get("target", "").lower().strip()
            if not src or not tgt:
                continue
            # Ensure nodes exist
            if not G.has_node(src):
                G.add_node(src, name=rel.get("source", src), type="concept", description="")
            if not G.has_node(tgt):
                G.add_node(tgt, name=rel.get("target", tgt), type="concept", description="")
            G.add_edge(
                src, tgt,
                type=rel.get("type", "related_to"),
                description=rel.get("description", ""),
            )
        self._save_graph(topic_id)

    def search_neighbors(self, topic_id: str, entity_name: str, hops: int = 2) -> Dict:
        """
        Return subgraph of nodes within `hops` from entity_name.
        Returns dict: { nodes: [...], edges: [...] }
        """
        G = self._load_graph(topic_id)
        node_id = entity_name.lower()

        if not G.has_node(node_id):
            return {"nodes": [], "edges": []}

        # BFS up to `hops` away
        subgraph_nodes: Set[str] = {node_id}
        frontier = {node_id}
        for _ in range(hops):
            new_frontier = set()
            for n in frontier:
                neighbors = set(G.successors(n)) | set(G.predecessors(n))
                new_frontier.update(neighbors - subgraph_nodes)
            subgraph_nodes.update(new_frontier)
            frontier = new_frontier

        sub = G.subgraph(subgraph_nodes)
        return {
            "nodes": [{"id": n, **sub.nodes[n]} for n in sub.nodes],
            "edges": [
                {"source": u, "target": v, **sub.edges[u, v]}
                for u, v in sub.edges
            ],
        }

    def find_relevant_entities(self, topic_id: str, query_terms: List[str]) -> List[Dict]:
        """
        Find graph nodes whose name/description matches any query term.
        Returns list of node dicts.
        """
        G = self._load_graph(topic_id)
        results = []
        query_lower = [t.lower() for t in query_terms]

        for node_id, attrs in G.nodes(data=True):
            name = attrs.get("name", node_id).lower()
            desc = attrs.get("description", "").lower()
            score = 0
            for term in query_lower:
                if term in name:
                    score += 2
                elif term in desc:
                    score += 1
            if score > 0:
                results.append({"id": node_id, "score": score, **attrs})

        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:10]

    def get_graph_stats(self, topic_id: str) -> Dict:
        """Return basic stats about the graph."""
        G = self._load_graph(topic_id)
        return {
            "node_count": G.number_of_nodes(),
            "edge_count": G.number_of_edges(),
        }

    def get_full_graph(self, topic_id: str) -> Dict:
        """Return full graph for visualization."""
        G = self._load_graph(topic_id)
        return {
            "nodes": [{"id": n, **G.nodes[n]} for n in G.nodes],
            "edges": [
                {"source": u, "target": v, **G.edges[u, v]}
                for u, v in G.edges
            ],
        }


# Singleton
graph_store = GraphStore()
