"""
Course Syllabus & Curriculum Engine.

Analyzes course inputs:
- Uploaded course materials and documents
- Stated learning objectives
- Assessment criteria / exam formats
- Course metadata and descriptions

Generates a hierarchical breakdown: Topics -> Subtopics -> Concepts,
and constructs the prerequisite dependency DAG.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List, Optional, Tuple

from app.rag.llm_client import llm_client
from app.tutoring.models import (
    ConceptNode,
    CourseInput,
    CurriculumKnowledgeMap,
    SubtopicNode,
    TopicNode,
)

logger = logging.getLogger(__name__)

SYLLABUS_ANALYSIS_PROMPT = """You are an expert curriculum architect and professor.
Analyze the provided course material and construct a rigorous, hierarchical Curriculum Knowledge Map.

COURSE SUBJECT: {subject}
COURSE INFO: {course_info}
LEARNING OBJECTIVES:
{objectives}
ASSESSMENT CRITERIA:
{criteria}

MATERIAL TEXT SAMPLE:
{sample_text}

Generate a structured curriculum breakdown strictly following this JSON schema:
{{
  "title": "Course Title",
  "subject": "{subject}",
  "topics": [
    {{
      "topic_id": "t1",
      "title": "Topic Title",
      "summary": "High-level summary of topic",
      "subtopics": [
        {{
          "subtopic_id": "st1_1",
          "title": "Subtopic Title",
          "concepts": [
            {{
              "concept_id": "c1_1_1",
              "title": "Concept Name",
              "description": "Clear academic definition and purpose",
              "difficulty": "foundational",  // "foundational", "intermediate", "advanced"
              "prerequisites": [],           // concept_ids that must be mastered first
              "key_terms": ["term1", "term2"]
            }}
          ]
        }}
      ]
    }}
  ]
}}

CRITICAL REQUIREMENTS:
1. Every concept MUST be atomic (teachable in a 15-30 minute focused session).
2. Prerequisite IDs must reference valid concept_ids defined earlier in the curriculum.
3. No emojis. Academic tone.
4. Output strictly valid JSON.
"""


class SyllabusEngine:
    """Engine parsing course inputs into hierarchical topics, subtopics, and concepts."""

    def __init__(self) -> None:
        self.llm = llm_client

    async def generate_knowledge_map(
        self,
        course_input: CourseInput,
        material_text: str = "",
    ) -> CurriculumKnowledgeMap:
        """Generates a complete CurriculumKnowledgeMap from course inputs."""
        objectives_str = "\n".join(f"- {o}" for o in course_input.learning_objectives) or "General mastery of subject"
        sample_text = material_text[:20000] if material_text else course_input.course_info

        prompt = SYLLABUS_ANALYSIS_PROMPT.format(
            subject=course_input.subject,
            course_info=course_input.course_info or course_input.subject,
            objectives=objectives_str,
            criteria=course_input.assessment_criteria or "Standard exam problem solving and conceptual understanding",
            sample_text=sample_text,
        )

        try:
            raw_response = await self.llm.generate(prompt)
            data = self._parse_json(raw_response)
        except Exception as exc:
            logger.warning("[SyllabusEngine] LLM curriculum generation notice: %s. Using heuristic fallback.", exc)
            data = self._heuristic_fallback(course_input, material_text)

        # Build models and compute prerequisite graph
        topics: List[TopicNode] = []
        dependency_graph: Dict[str, List[str]] = {}

        for t_idx, t_data in enumerate(data.get("topics", []), start=1):
            topic_id = t_data.get("topic_id") or f"topic_{t_idx}"
            subtopics: List[SubtopicNode] = []

            for st_idx, st_data in enumerate(t_data.get("subtopics", []), start=1):
                subtopic_id = st_data.get("subtopic_id") or f"{topic_id}_st{st_idx}"
                concepts: List[ConceptNode] = []

                for c_idx, c_data in enumerate(st_data.get("concepts", []), start=1):
                    concept_id = c_data.get("concept_id") or f"{subtopic_id}_c{c_idx}"
                    prereqs = c_data.get("prerequisites", [])

                    concept = ConceptNode(
                        concept_id=concept_id,
                        title=c_data.get("title", f"Concept {c_idx}"),
                        description=c_data.get("description", ""),
                        difficulty=c_data.get("difficulty", "intermediate"),
                        prerequisites=prereqs,
                        key_terms=c_data.get("key_terms", []),
                    )
                    concepts.append(concept)
                    dependency_graph[concept_id] = prereqs

                subtopics.append(
                    SubtopicNode(
                        subtopic_id=subtopic_id,
                        title=st_data.get("title", f"Subtopic {st_idx}"),
                        concepts=concepts,
                    )
                )

            topics.append(
                TopicNode(
                    topic_id=topic_id,
                    title=t_data.get("title", f"Topic {t_idx}"),
                    summary=t_data.get("summary", ""),
                    subtopics=subtopics,
                )
            )

        return CurriculumKnowledgeMap(
            course_id=course_input.course_id,
            subject=data.get("subject", course_input.subject),
            title=data.get("title", f"{course_input.subject} Curriculum"),
            topics=topics,
            dependency_graph=dependency_graph,
        )

    def _parse_json(self, text: str) -> Dict[str, Any]:
        """Robustly extracts JSON dictionary from LLM response."""
        cleaned = text.strip()
        if cleaned.startswith("```"):
            cleaned = re.sub(r"^```(?:json)?", "", cleaned).strip()
            cleaned = re.sub(r"```$", "", cleaned).strip()

        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start != -1 and end != -1:
            return json.loads(cleaned[start : end + 1])
        return json.loads(cleaned)

    def _heuristic_fallback(
        self, course_input: CourseInput, material_text: str
    ) -> Dict[str, Any]:
        """Heuristic syllabus breakdown when LLM call is unavailable."""
        subject = course_input.subject or "Course Material"
        lines = [line.strip() for line in material_text.splitlines() if len(line.strip()) > 10]
        sample_title = lines[0] if lines else f"{subject} Fundamentals"

        return {
            "title": f"{subject} Core Study Curriculum",
            "subject": subject,
            "topics": [
                {
                    "topic_id": "topic_1",
                    "title": sample_title[:60],
                    "summary": f"Foundational principles and core concepts in {subject}.",
                    "subtopics": [
                        {
                            "subtopic_id": "st_1",
                            "title": "Foundational Mechanics",
                            "concepts": [
                                {
                                    "concept_id": "c_1",
                                    "title": f"Introduction to {subject}",
                                    "description": f"Core governing framework of {subject}.",
                                    "difficulty": "foundational",
                                    "prerequisites": [],
                                    "key_terms": [subject],
                                },
                                {
                                    "concept_id": "c_2",
                                    "title": f"Key Governing Equations in {subject}",
                                    "description": f"Quantitative formulations and applications in {subject}.",
                                    "difficulty": "intermediate",
                                    "prerequisites": ["c_1"],
                                    "key_terms": ["formulation", "equations"],
                                },
                            ],
                        }
                    ],
                }
            ],
        }


syllabus_engine = SyllabusEngine()
