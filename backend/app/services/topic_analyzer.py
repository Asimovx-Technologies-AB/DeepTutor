import json
import logging
import math
from typing import List, Dict, Any
from sqlalchemy.orm import Session

from app.models.chunk import KnowledgeChunk
from app.models.topic_analysis import DocumentTopicAnalysis, ExtractedTopic
from app.services.llm_service import default_llm_service

logger = logging.getLogger(__name__)

# Configurable Scoring Weights
SCORING_WEIGHTS = {
    "structural": 0.15,
    "frequency": 0.10,
    "definition": 0.15,
    "depth": 0.15,
    "formula": 0.10,
    "examples": 0.05,
    "summary": 0.10,
    "questions": 0.10,
    "cross_section": 0.05,
    "learning_objective": 0.05
}

LOCAL_EXTRACTION_PROMPT = """
You are the Topic Analysis Engine of DeepTutor.
Analyze the following document sections/chunks and identify meaningful educational topics, subtopics, and evidence of importance.

IMPORTANT RULES:
- Do NOT hallucinate topics. Every extracted topic MUST exist in the provided text.
- Do NOT claim a topic has high exam probability unless explicitly stated in the text (e.g., "This is frequently tested").
- Preserve the document hierarchy. Distinguish major concepts from minor mentions.
- Provide concrete evidence for importance from the text itself.

For each candidate topic, provide:
- "topic": The clean, normalized topic name
- "chapter": The parent chapter or section
- "definitions_present": boolean
- "formula_present": boolean
- "examples_present": boolean
- "questions_present": boolean
- "summary_present": boolean
- "learning_objective_present": boolean
- "evidence": Array of strings explaining why this is important based ONLY on the text
- "source_pages": Array of integers
- "prerequisites": Array of strings (other topics required to understand this)
- "related_topics": Array of strings
- "subtopics": Array of strings

Return the output as a strictly valid JSON object with a key "candidates" containing an array of objects matching the above structure.
"""

GLOBAL_CONSOLIDATION_PROMPT = """
You are the Topic Consolidation Engine.
Given a list of extracted candidate topics from multiple document batches, your task is to merge duplicates, normalize names (e.g., "ANN" and "Artificial Neural Network" -> "Artificial Neural Network"), and consolidate their evidence and source pages.

Return the consolidated list as a strictly valid JSON object with a key "topics" containing the merged array of objects.
Preserve all boolean signals (if any duplicate had True, the merged one should have True).
"""

class TopicAnalysisService:
    
    @classmethod
    def analyze_document_topics(cls, db: Session, document_id: str) -> str:
        """
        Orchestrates the 4-stage topic extraction and importance analysis pipeline.
        Returns the ID of the DocumentTopicAnalysis record.
        """
        # Create analysis record
        analysis = DocumentTopicAnalysis(
            document_id=document_id,
            status="PROCESSING"
        )
        db.add(analysis)
        db.commit()
        db.refresh(analysis)
        
        try:
            # 1. Fetch chunks
            chunks = db.query(KnowledgeChunk).filter(KnowledgeChunk.document_id == document_id).order_by(KnowledgeChunk.page_number).all()
            if not chunks:
                analysis.status = "COMPLETED"
                db.commit()
                return analysis.id

            # 2. Local Batch Extraction
            candidates = cls._local_batch_extraction(chunks)
            
            # 3. Global Consolidation
            consolidated_topics = cls._global_consolidation(candidates)
            
            # 4. Importance Scoring
            scored_topics = cls._calculate_scores(consolidated_topics)
            
            # 5. Coverage validation (Stage 5)
            chapters_in_doc = set(c.chapter for c in chunks if c.chapter)
            chapters_with_topics = set(t.get("chapter") for t in scored_topics if t.get("chapter"))
            missing_chapters = chapters_in_doc - chapters_with_topics
            if missing_chapters:
                missing_chunks = [c for c in chunks if c.chapter in missing_chapters]
                if missing_chunks:
                    extra_candidates = cls._local_batch_extraction(missing_chunks)
                    if extra_candidates:
                        extra_scored = cls._calculate_scores(cls._global_consolidation(extra_candidates))
                        scored_topics.extend(extra_scored)
            
            # 5. Persist to DB
            analysis.total_topics = len(scored_topics)
            for t_data in scored_topics:
                topic_record = ExtractedTopic(
                    analysis_id=analysis.id,
                    topic=t_data["topic"],
                    chapter=t_data.get("chapter"),
                    importance_score=t_data["importance_score"],
                    importance_level=t_data["importance_level"],
                    definitions_present=t_data.get("definitions_present", False),
                    formula_present=t_data.get("formula_present", False),
                    examples_present=t_data.get("examples_present", False),
                    questions_present=t_data.get("questions_present", False),
                    summary_present=t_data.get("summary_present", False),
                    learning_objective_present=t_data.get("learning_objective_present", False),
                    evidence=t_data.get("evidence", []),
                    source_pages=t_data.get("source_pages", []),
                    prerequisites=t_data.get("prerequisites", []),
                    related_topics=t_data.get("related_topics", []),
                    subtopics=t_data.get("subtopics", [])
                )
                db.add(topic_record)
            
            analysis.status = "COMPLETED"
            db.commit()
            
        except Exception as e:
            logger.error(f"Topic Analysis failed for document {document_id}: {e}")
            analysis.status = "FAILED"
            db.commit()
            
        return analysis.id

    @classmethod
    def _local_batch_extraction(cls, chunks: List[KnowledgeChunk]) -> List[Dict[str, Any]]:
        # Batch chunks to avoid exceeding token limits
        batch_size = 20
        all_candidates = []
        
        for i in range(0, len(chunks), batch_size):
            batch = chunks[i:i + batch_size]
            chunk_texts = [f"Page {c.page_number} ({c.chunk_type}): {c.content}" for c in batch]
            content = "\n---\n".join(chunk_texts)
            
            try:
                resp = default_llm_service.generate(
                    system_prompt=LOCAL_EXTRACTION_PROMPT,
                    prompt=f"Extract topics from this batch:\n\n{content}"
                )
                
                if isinstance(resp, str):
                    import re
                    json_match = re.search(r'\{.*\}', resp, re.DOTALL)
                    if json_match:
                        parsed = json.loads(json_match.group(0))
                    else:
                        parsed = json.loads(resp)
                else:
                    parsed = resp
                    
                candidates = parsed.get("candidates", [])
                all_candidates.extend(candidates)
            except Exception as e:
                logger.warning(f"Failed local batch extraction: {e}")
                
        return all_candidates

    @classmethod
    def _global_consolidation(cls, candidates: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        if not candidates:
            return []
            
        try:
            resp = default_llm_service.generate(
                system_prompt=GLOBAL_CONSOLIDATION_PROMPT,
                prompt=f"Consolidate these candidates:\n\n{json.dumps(candidates)}"
            )
            if isinstance(resp, str):
                import re
                json_match = re.search(r'\{.*\}', resp, re.DOTALL)
                if json_match:
                    parsed = json.loads(json_match.group(0))
                else:
                    parsed = json.loads(resp)
            else:
                parsed = resp
                
            return parsed.get("topics", [])
        except Exception as e:
            logger.warning(f"Failed global consolidation: {e}")
            return candidates

    @classmethod
    def _calculate_scores(cls, topics: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        for t in topics:
            score = 0.0
            
            if t.get("definitions_present"): score += SCORING_WEIGHTS["definition"]
            if t.get("formula_present"): score += SCORING_WEIGHTS["formula"]
            if t.get("examples_present"): score += SCORING_WEIGHTS["examples"]
            if t.get("questions_present"): score += SCORING_WEIGHTS["questions"]
            if t.get("summary_present"): score += SCORING_WEIGHTS["summary"]
            if t.get("learning_objective_present"): score += SCORING_WEIGHTS["learning_objective"]
            
            # Simple heuristic: longer evidence/source_pages array implies higher depth/frequency
            evidence_count = len(t.get("evidence", []))
            pages_count = len(t.get("source_pages", []))
            
            if evidence_count > 2: score += SCORING_WEIGHTS["depth"]
            elif evidence_count > 0: score += (SCORING_WEIGHTS["depth"] * 0.5)
            
            if pages_count > 3: score += SCORING_WEIGHTS["frequency"]
            elif pages_count > 1: score += (SCORING_WEIGHTS["frequency"] * 0.5)
            
            if len(t.get("prerequisites", [])) > 0: score += SCORING_WEIGHTS["structural"]
            
            # Cap at 1.0
            t["importance_score"] = min(round(score, 2), 1.0)
            
            if t["importance_score"] >= 0.7:
                t["importance_level"] = "HIGH"
            elif t["importance_score"] >= 0.4:
                t["importance_level"] = "MEDIUM"
            else:
                t["importance_level"] = "LOW"
                
        # Sort by score descending
        topics.sort(key=lambda x: x.get("importance_score", 0), reverse=True)
        return topics

    @classmethod
    def get_or_run_analysis(cls, db: Session, document_id: str) -> DocumentTopicAnalysis:
        """
        Returns cached analysis if COMPLETED and document unchanged.
        Otherwise runs analysis synchronously and returns result.
        """
        analysis = db.query(DocumentTopicAnalysis).filter(
            DocumentTopicAnalysis.document_id == document_id
        ).order_by(DocumentTopicAnalysis.created_at.desc()).first()
        
        if analysis and analysis.status in ("COMPLETED", "PROCESSING"):
            return analysis
            
        analysis_id = cls.analyze_document_topics(db, document_id)
        return db.query(DocumentTopicAnalysis).filter(DocumentTopicAnalysis.id == analysis_id).first()

    @classmethod
    def format_analysis_for_chat(cls, db: Session, analysis: DocumentTopicAnalysis) -> str:
        """
        Formats the DocumentTopicAnalysis + ExtractedTopic records into a student-friendly markdown response.
        """
        if analysis.status != "COMPLETED":
            return "Topic analysis is not completed yet."
            
        topics = db.query(ExtractedTopic).filter(ExtractedTopic.analysis_id == analysis.id).order_by(ExtractedTopic.importance_score.desc()).all()
        if not topics:
            return "No important topics were identified in this document."
            
        # Group by chapter
        by_chapter = {}
        for t in topics:
            ch = t.chapter or "General Concepts"
            if ch not in by_chapter:
                by_chapter[ch] = []
            by_chapter[ch].append(t)
            
        response = "### Important Topics Analysis\n\nBased on the document structure and content, here are the most important topics to focus on:\n\n"
        
        for ch, ch_topics in by_chapter.items():
            response += f"#### {ch}\n"
            for t in ch_topics:
                level_marker = "🔴" if t.importance_level == "HIGH" else "🟡" if t.importance_level == "MEDIUM" else "🟢"
                response += f"- {level_marker} **{t.topic}** (Score: {t.importance_score})\n"
                if t.evidence:
                    response += f"  - *Why it's important:* {t.evidence[0]}\n"
                if t.subtopics:
                    response += f"  - *Subtopics:* {', '.join(t.subtopics[:3])}\n"
            response += "\n"
            
        return response
