import re
import json
import logging
from typing import List, Dict, Any, Optional
from app.services.llm_service import default_llm_service

logger = logging.getLogger(__name__)

_CURRICULUM_SYSTEM_PROMPT = """You are an elite AI Pedagogical Curriculum Director and Master Academic Tutor.
Your mission is to analyze the extracted excerpts and table of contents of an uploaded academic study document, and decide the definitive list of the MOST IMPORTANT TOPICS that a student needs to master.

You must return ONLY a single valid JSON object adhering strictly to this format:
{
  "document_title": "Official or concise inferred title of the document",
  "subject_domain": "e.g. Machine Learning, Physics, Calculus, Organic Chemistry, etc.",
  "executive_summary": "2-3 sentence high-level overview of what this material covers and its core focus",
  "important_topics": [
    {
      "order": 1,
      "title": "Clear, precise topic title",
      "summary": "1-2 sentence intuitive explanation of what this topic is and why it matters",
      "difficulty": "Beginner" | "Intermediate" | "Advanced",
      "estimated_study_time": "15 mins" | "25 mins" | "40 mins",
      "key_concepts": ["Concept 1", "Concept 2", "Concept 3"],
      "suggested_question": "A natural student question to start learning this topic (e.g. 'Can you explain linear regression with a simple intuitive example?')"
    }
  ],
  "recommended_starting_topic": "Title of the best topic to begin with",
  "welcome_briefing_markdown": "A concise, student-friendly introductory markdown overview listing ONLY the important topics with bold bullet points, a brief description of each, and clear guidance on asking questions to begin."
}

Rules:
1. Synthesize between 4 and 8 high-priority, conceptually significant topics.
2. Avoid generic titles like 'Chapter 1' or 'Introduction'. Use clear, academic topic names (e.g., 'Convolutional Neural Networks & Feature Maps', 'Electromagnetic Induction & Faraday\\'s Law').
3. Ensure the JSON is 100% valid and free of markdown wrap markers.
"""


class CurriculumSynthesizer:
    """
    LLM-powered Curriculum Synthesizer.
    Analyzes document text chunks and structural headers to extract and prioritize
    the most important learning topics, syllabus hierarchy, and starter questions.
    """

    @classmethod
    def synthesize_curriculum(
        cls,
        document_title: str,
        chunks_sample: List[Dict[str, Any]],
        existing_toc: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Calls the live LLM to analyze the document and determine the list of important topics.
        Falls back to a high-quality deterministic heuristic synthesis if the LLM is offline.
        """
        # Prepare context samples
        sample_texts = []
        for c in chunks_sample[:15]:
            snippet = (c.get("content") or c.get("search_text") or "").strip()
            if snippet:
                sample_texts.append(f"[Page {c.get('page_number', 1)} | Topic: {c.get('topic', 'General')}]:\n{snippet[:400]}")

        combined_samples = "\n\n".join(sample_texts)
        toc_context = f"\nExisting Table of Contents / Headings:\n" + "\n".join([f"- {t}" for t in (existing_toc or [])[:20]]) if existing_toc else ""

        # 1. Attempt LLM Synthesis
        if default_llm_service.is_live_model_configured():
            try:
                user_prompt = (
                    f"Document Title: {document_title}\n"
                    f"{toc_context}\n\n"
                    f"Sample Content Excerpts:\n{combined_samples}\n\n"
                    f"Please analyze the material above and determine the core important topics according to the JSON format."
                )
                llm_output = default_llm_service.generate(
                    prompt=user_prompt,
                    system_prompt=_CURRICULUM_SYSTEM_PROMPT
                )
                if llm_output:
                    cleaned_json = re.sub(r"```(?:json)?", "", llm_output).strip().strip("`").strip()
                    parsed = json.loads(cleaned_json)
                    if isinstance(parsed, dict) and "important_topics" in parsed and len(parsed["important_topics"]) > 0:
                        logger.info(f"[CurriculumSynthesizer] Successfully synthesized {len(parsed['important_topics'])} topics via LLM for {document_title}")
                        return parsed
            except Exception as e:
                logger.warning(f"[CurriculumSynthesizer] LLM curriculum synthesis failed, using fallback: {e}")

        # 2. Deterministic Fallback Synthesis
        return cls._fallback_curriculum_synthesis(document_title, chunks_sample, existing_toc)

    @classmethod
    def _fallback_curriculum_synthesis(
        cls,
        document_title: str,
        chunks_sample: List[Dict[str, Any]],
        existing_toc: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Rule-based deterministic synthesis when LLM is offline.
        """
        topics_list = []
        seen_titles = set()

        if existing_toc:
            for idx, t in enumerate(existing_toc[:8]):
                clean_t = re.sub(r"^(?:chapter|section|\d+[\.\s]+)\s*", "", t, flags=re.IGNORECASE).strip()
                if clean_t and clean_t.lower() not in seen_titles:
                    seen_titles.add(clean_t.lower())
                    topics_list.append({
                        "order": idx + 1,
                        "title": clean_t.title() if len(clean_t) > 3 else clean_t.upper(),
                        "summary": f"Key concepts and foundational principles covering {clean_t}.",
                        "difficulty": "Intermediate",
                        "estimated_study_time": "20 mins",
                        "key_concepts": [w for w in clean_t.split() if len(w) > 3],
                        "suggested_question": f"Can you give me an overview and core formulas for {clean_t}?"
                    })

        if not topics_list:
            # Infer from chunk topics
            for c in chunks_sample:
                top = c.get("topic") or c.get("chapter_section")
                if top and top not in ("General", "Unknown") and top.lower() not in seen_titles:
                    seen_titles.add(top.lower())
                    topics_list.append({
                        "order": len(topics_list) + 1,
                        "title": top.title() if len(top) > 3 else top.upper(),
                        "summary": f"Core study concepts and examples regarding {top}.",
                        "difficulty": "Intermediate",
                        "estimated_study_time": "20 mins",
                        "key_concepts": [w for w in top.split() if len(w) > 3],
                        "suggested_question": f"Explain the key principles of {top} step-by-step."
                    })
                if len(topics_list) >= 6:
                    break

        if not topics_list:
            topics_list.append({
                "order": 1,
                "title": f"Core Concepts: {document_title}",
                "summary": "Foundational theory, definitions, and technical examples from the material.",
                "difficulty": "Intermediate",
                "estimated_study_time": "25 mins",
                "key_concepts": ["Fundamentals", "Applications", "Formulas"],
                "suggested_question": f"What are the most important takeaways from {document_title}?"
            })

        # Build welcome markdown
        topic_bullets = "\n".join([
            f"- **{t['order']}. {t['title']}** ({t['difficulty']} • {t['estimated_study_time']})\n  {t['summary']}"
            for t in topics_list
        ])

        markdown_overview = (
            f"### 📚 Important Topics in **{document_title}**\n\n"
            f"I have analyzed your study material and mapped out the core learning curriculum:\n\n"
            f"{topic_bullets}\n\n"
            f"💡 **How to start:** Ask me to explain any specific concept, solve exercises, or generate revision notes!"
        )

        return {
            "document_title": document_title,
            "subject_domain": "General Study",
            "executive_summary": f"Comprehensive study material covering core concepts and exercises for {document_title}.",
            "important_topics": topics_list,
            "recommended_starting_topic": topics_list[0]["title"],
            "welcome_briefing_markdown": markdown_overview
        }
