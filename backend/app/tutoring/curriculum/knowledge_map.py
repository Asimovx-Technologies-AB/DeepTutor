"""
Curriculum Knowledge Map Resolver & Advanced Graph Analytics Engine.

Validates the curriculum dependency DAG, detects cycles, calculates topological
learning sequences, performs transitive reduction to remove redundant prerequisites,
computes critical path bottlenecks, and enriches ConceptNodes with extracted figures,
tables, and formulas from the PostgreSQL document_chunks store.
"""
from __future__ import annotations

import logging
from collections import defaultdict, deque
from typing import Any, Dict, List, Optional, Set, Tuple

from sqlalchemy import text

from app.core.database import engine
from app.tutoring.models import (
    ConceptNode,
    CurriculumKnowledgeMap,
    SubtopicNode,
    TopicNode,
)

logger = logging.getLogger(__name__)


class KnowledgeMapResolver:
    """Service to validate, enrich, analyze, and query CurriculumKnowledgeMaps."""

    def __init__(self) -> None:
        self.engine = engine

    def get_all_concepts(self, km: CurriculumKnowledgeMap) -> Dict[str, ConceptNode]:
        """Returns a flat lookup map of concept_id -> ConceptNode."""
        concepts: Dict[str, ConceptNode] = {}
        for topic in km.topics:
            for subtopic in topic.subtopics:
                for concept in subtopic.concepts:
                    concepts[concept.concept_id] = concept
        return concepts

    def get_concept_by_id(
        self, km: CurriculumKnowledgeMap, concept_id: str
    ) -> Optional[ConceptNode]:
        """Finds a specific concept node by ID."""
        for topic in km.topics:
            for subtopic in topic.subtopics:
                for concept in subtopic.concepts:
                    if concept.concept_id == concept_id:
                        return concept
        return None

    def validate_dag(self, km: CurriculumKnowledgeMap) -> List[str]:
        """
        Validates the prerequisite graph:
        1. Confirms all prerequisite references point to valid concepts in the curriculum.
        2. Detects dependency cycles using Kahn's algorithm.
        """
        errors: List[str] = []
        concepts = self.get_all_concepts(km)

        # 1. Check for missing prerequisite references
        for cid, prereqs in km.dependency_graph.items():
            if cid not in concepts:
                errors.append(f"Graph refers to unknown target concept '{cid}'.")
            for pid in prereqs:
                if pid not in concepts:
                    errors.append(f"Concept '{cid}' references unknown prerequisite '{pid}'.")

        # 2. Check for cycles via Kahn's algorithm
        in_degree: Dict[str, int] = {cid: 0 for cid in concepts}
        adj_list: Dict[str, List[str]] = defaultdict(list)

        for cid, prereqs in km.dependency_graph.items():
            for pid in prereqs:
                if pid in concepts and cid in concepts:
                    adj_list[pid].append(cid)
                    in_degree[cid] += 1

        queue = deque([cid for cid, deg in in_degree.items() if deg == 0])
        visited_count = 0

        while queue:
            curr = queue.popleft()
            visited_count += 1
            for neighbor in adj_list[curr]:
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        if visited_count < len(concepts):
            errors.append("Curriculum prerequisite graph contains a dependency cycle.")

        return errors

    def get_topological_sequence(
        self, km: CurriculumKnowledgeMap
    ) -> List[ConceptNode]:
        """
        Computes the canonical learning sequence of concepts using topological sort.
        Ensures foundational prerequisites are always learned before dependent concepts.
        """
        concepts = self.get_all_concepts(km)
        in_degree: Dict[str, int] = {cid: 0 for cid in concepts}
        adj_list: Dict[str, List[str]] = defaultdict(list)

        for cid, prereqs in km.dependency_graph.items():
            for pid in prereqs:
                if pid in concepts and cid in concepts:
                    adj_list[pid].append(cid)
                    in_degree[cid] += 1

        queue = deque([cid for cid, deg in in_degree.items() if deg == 0])
        sorted_nodes: List[ConceptNode] = []

        while queue:
            curr_id = queue.popleft()
            sorted_nodes.append(concepts[curr_id])
            for nxt_id in adj_list[curr_id]:
                in_degree[nxt_id] -= 1
                if in_degree[nxt_id] == 0:
                    queue.append(nxt_id)

        visited_ids = {node.concept_id for node in sorted_nodes}
        for cid, node in concepts.items():
            if cid not in visited_ids:
                sorted_nodes.append(node)

        return sorted_nodes

    def transitive_reduction(
        self, km: CurriculumKnowledgeMap
    ) -> Dict[str, List[str]]:
        """
        Computes the transitive reduction of the prerequisite graph.
        Removes redundant transitive edges (e.g. if A -> B and B -> C, then direct A -> C is pruned).
        Returns a simplified dependency graph.
        """
        concepts = self.get_all_concepts(km)
        adj_list: Dict[str, Set[str]] = defaultdict(set)

        for cid, prereqs in km.dependency_graph.items():
            for pid in prereqs:
                if pid in concepts and cid in concepts:
                    adj_list[pid].add(cid)

        # Reachability via DFS
        def _get_reachable(start: str, skip_direct: str) -> Set[str]:
            visited: Set[str] = set()
            stack = [nbr for nbr in adj_list.get(start, set()) if nbr != skip_direct]
            while stack:
                curr = stack.pop()
                if curr not in visited:
                    visited.add(curr)
                    stack.extend(adj_list.get(curr, set()))
            return visited

        reduced: Dict[str, List[str]] = defaultdict(list)
        for pid, targets in list(adj_list.items()):
            for target in targets:
                # If target is reachable without direct edge, direct edge is redundant
                indirect = _get_reachable(pid, skip_direct=target)
                if target not in indirect:
                    reduced[target].append(pid)

        return dict(reduced)

    def compute_critical_path(
        self, km: CurriculumKnowledgeMap
    ) -> Tuple[int, List[str]]:
        """
        Computes the critical path (longest sequential prerequisite chain) in the curriculum.
        Returns (max_depth, list_of_concept_ids_along_critical_path).
        """
        concepts = self.get_all_concepts(km)
        if not concepts:
            return 0, []

        adj_list: Dict[str, List[str]] = defaultdict(list)
        in_degree: Dict[str, int] = {cid: 0 for cid in concepts}

        for cid, prereqs in km.dependency_graph.items():
            for pid in prereqs:
                if pid in concepts and cid in concepts:
                    adj_list[pid].append(cid)
                    in_degree[cid] += 1

        # Dynamic programming on DAG for longest path
        longest_dist: Dict[str, int] = {cid: 1 for cid in concepts}
        parent: Dict[str, Optional[str]] = {cid: None for cid in concepts}

        queue = deque([cid for cid, deg in in_degree.items() if deg == 0])
        while queue:
            curr = queue.popleft()
            for nbr in adj_list[curr]:
                if longest_dist[curr] + 1 > longest_dist[nbr]:
                    longest_dist[nbr] = longest_dist[curr] + 1
                    parent[nbr] = curr
                in_degree[nbr] -= 1
                if in_degree[nbr] == 0:
                    queue.append(nbr)

        if not longest_dist:
            return 0, []

        end_node = max(longest_dist, key=lambda k: longest_dist[k])
        max_depth = longest_dist[end_node]

        # Reconstruct path
        path = []
        curr: Optional[str] = end_node
        while curr:
            path.append(curr)
            curr = parent.get(curr)
        path.reverse()

        return max_depth, path

    def compute_concept_centrality(
        self, km: CurriculumKnowledgeMap
    ) -> Dict[str, float]:
        """
        Calculates downstream influence centrality for each concept.
        Higher scores indicate foundational concepts that unlock multiple subsequent units.
        """
        concepts = self.get_all_concepts(km)
        total = len(concepts)
        if total <= 1:
            return {cid: 1.0 for cid in concepts}

        adj_list: Dict[str, List[str]] = defaultdict(list)
        for cid, prereqs in km.dependency_graph.items():
            for pid in prereqs:
                if pid in concepts and cid in concepts:
                    adj_list[pid].append(cid)

        centrality: Dict[str, float] = {}
        for cid in concepts:
            visited = set()
            stack = list(adj_list[cid])
            while stack:
                curr = stack.pop()
                if curr not in visited:
                    visited.add(curr)
                    stack.extend(adj_list[curr])
            # Ratio of downstream concepts unlocked
            centrality[cid] = round(len(visited) / (total - 1), 3)

        return centrality

    def get_prerequisites(
        self, km: CurriculumKnowledgeMap, concept_id: str
    ) -> List[ConceptNode]:
        """Returns direct prerequisite ConceptNodes for a concept."""
        prereq_ids = km.dependency_graph.get(concept_id, [])
        concepts = self.get_all_concepts(km)
        return [concepts[pid] for pid in prereq_ids if pid in concepts]

    def get_unlocked_concepts(
        self, km: CurriculumKnowledgeMap, concept_id: str
    ) -> List[ConceptNode]:
        """Returns concepts that directly list this concept as a prerequisite."""
        concepts = self.get_all_concepts(km)
        unlocked: List[ConceptNode] = []
        for cid, prereqs in km.dependency_graph.items():
            if concept_id in prereqs and cid in concepts:
                unlocked.append(concepts[cid])
        return unlocked

    def enrich_concepts_with_assets(
        self,
        km: CurriculumKnowledgeMap,
        session_id_or_doc_id: str,
    ) -> None:
        """
        Queries PostgreSQL document_chunks for extracted figures, tables, and formulas
        and associates their IDs with relevant concepts based on title and key terms.
        """
        try:
            query = text("""
                SELECT chunk_id, box_type, caption, latex_equations, is_table_or_figure, chunk_text
                FROM document_chunks
                WHERE (session_id = :sid OR doc_id = :sid OR topic_id = :sid)
                  AND (
                      box_type IN ('figure', 'table', 'diagram', 'formula', 'theorem', 'definition', 'example', 'exercise')
                      OR is_table_or_figure = true
                      OR latex_equations IS NOT NULL
                  )
                LIMIT 200
            """)
            with self.engine.connect() as conn:
                rows = conn.execute(query, {"sid": session_id_or_doc_id}).mappings().fetchall()

            if not rows:
                return

            for topic in km.topics:
                for subtopic in topic.subtopics:
                    for concept in subtopic.concepts:
                        search_terms = {concept.title.lower()} | {t.lower() for t in concept.key_terms}
                        matched_box_ids: Set[str] = set(concept.knowledge_box_ids)

                        for row in rows:
                            cid = str(row["chunk_id"])
                            c_text = (row.get("chunk_text") or "").lower()
                            caption = (row.get("caption") or "").lower()

                            if any(st in c_text or st in caption for st in search_terms if len(st) > 2):
                                matched_box_ids.add(cid)

                        concept.knowledge_box_ids = list(matched_box_ids)

        except Exception as exc:
            logger.debug("[KnowledgeMapResolver] enrich_concepts_with_assets notice: %s", exc)


knowledge_map_resolver = KnowledgeMapResolver()
