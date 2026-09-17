import time
import logging
from typing import Dict, Any, Optional
from sqlalchemy.orm import Session
from app.models.document import Document
from app.storage.local_storage import default_storage
from app.pipeline.metadata_extractor import MetadataExtractor
from app.pipeline.pdf_parser import PyMuPDFParser
from app.pipeline.classifier import DocumentClassifier
from app.pipeline.text_pipeline.quality_checker import TextQualityChecker
from app.pipeline.text_pipeline.vlm_fallback import VLMFallbackExtractor
from app.pipeline.text_pipeline.normalizer import TextNormalizer
from app.pipeline.visual_pipeline.layout_analyzer import LayoutAnalyzer
from app.pipeline.visual_pipeline.table_detector import TableDetector
from app.pipeline.visual_pipeline.formula_detector import FormulaDetector
from app.pipeline.structure_builder import DocumentStructureBuilder
from app.pipeline.semantic_extractor import SemanticKnowledgeExtractor
from app.pipeline.chunker import KnowledgeChunker
from app.pipeline.quality_validator import QualityValidator
from app.pipeline.canonical import CanonicalDocumentBuilder
from app.services.storage_pipeline import DataStoragePipeline
from app.schemas.document import CanonicalDocumentRepresentation

logger = logging.getLogger(__name__)


class DocumentPipelineOrchestrator:
    """
    Central State Machine Orchestrator for the Document Processing and Storage Architecture.
    Executes all pipeline stages deterministically with timing, metrics, and error handling.
    """

    @classmethod
    def process_document(
        cls,
        session: Session,
        file_bytes: bytes,
        filename: str,
        existing_doc_id: Optional[str] = None,
        document_type: str = "STUDY_MATERIAL"
    ) -> CanonicalDocumentRepresentation:
        start_time = time.time()
        stage_durations: Dict[str, float] = {}

        # 1. Object Storage: Store raw uploaded PDF
        t0 = time.time()
        raw_storage_path = default_storage.store_file(file_bytes, filename, subfolder="raw_documents")
        stage_durations["OBJECT_STORAGE"] = round((time.time() - t0) * 1000, 2)

        # 2. Metadata Extraction
        t0 = time.time()
        meta_dict = MetadataExtractor.extract_pdf_metadata(file_bytes, filename)
        stage_durations["METADATA_EXTRACTION"] = round((time.time() - t0) * 1000, 2)

        # Check or generate document ID
        file_hash = meta_dict["file_hash"]
        db_doc = session.query(Document).filter(Document.file_hash == file_hash).first()
        if db_doc:
            doc_id = db_doc.id
        elif existing_doc_id:
            doc_id = existing_doc_id
        else:
            import uuid
            doc_id = str(uuid.uuid4())

        meta_dict["id"] = doc_id
        meta_dict["status"] = "PARSING"
        meta_dict["current_stage"] = "PYMUPDF_PARSER"

        # 3. PyMuPDF Parser: High-fidelity layout, spans, and page rendering
        t0 = time.time()
        parser = PyMuPDFParser(render_dpi=100)
        pages_data = parser.parse_document(file_bytes, doc_id)
        stage_durations["PYMUPDF_PARSER"] = round((time.time() - t0) * 1000, 2)

        # 4. Document Classification
        t0 = time.time()
        doc_classification = DocumentClassifier.classify_document(pages_data)
        stage_durations["CLASSIFICATION"] = round((time.time() - t0) * 1000, 2)
        is_scanned_doc = doc_classification.get("overall_classification") in ("scanned", "hybrid")

        # 5. Dual Pipeline Execution (Text Pipeline + Visual Pipeline) - Parallelized across CPU threads
        t0 = time.time()
        all_tables = []
        all_formulas = []

        def _process_page_worker(page):
            page_num = page["page_number"]
            raw_text = page["raw_text"]

            # Branch A: Text Quality Check
            q_score, decision = TextQualityChecker.evaluate_quality(raw_text)
            page["quality_score"] = q_score

            has_no_text = not raw_text or not raw_text.strip()
            if (decision == "POOR" and is_scanned_doc) or has_no_text:
                normalized_text = VLMFallbackExtractor.process_scanned_page(page)
                page["classification"] = "scanned"
            else:
                normalized_text = TextNormalizer.normalize(raw_text)
                page["classification"] = "digital"

            page["normalized_text"] = normalized_text

            # Branch B: Structure, Table & Formula Extraction (Refresh blocks updated by VLM if applicable)
            blocks = page.get("blocks", [])
            blocks = LayoutAnalyzer.analyze_page_layout(blocks, page["width"], page["height"])
            page_tables, blocks = TableDetector.detect_tables(blocks, page_num, native_tables=page.get("native_tables"))
            page_formulas, blocks = FormulaDetector.detect_formulas(blocks, page_num)
            page["blocks"] = blocks
            return page, page_tables, page_formulas

        import concurrent.futures
        # Limit worker concurrency for scanned docs to avoid VLM API quota exhaustion
        pool_limit = 4 if is_scanned_doc else 8
        max_workers = min(pool_limit, max(1, len(pages_data)))
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            processed_results = list(executor.map(_process_page_worker, pages_data))

        pages_data = [r[0] for r in processed_results]
        for r in processed_results:
            all_tables.extend(r[1])
            all_formulas.extend(r[2])

        stage_durations["DUAL_PIPELINE"] = round((time.time() - t0) * 1000, 2)

        # 6. Document Structure Builder
        t0 = time.time()
        structure_tree = DocumentStructureBuilder.build_structure(pages_data)
        stage_durations["STRUCTURE_BUILDER"] = round((time.time() - t0) * 1000, 2)

        # 7. Knowledge Chunking (14 Dimensions)
        t0 = time.time()
        chunks = KnowledgeChunker.generate_chunks(
            doc_id=doc_id,
            pages_data=pages_data,
            structure_tree=structure_tree,
            tables=all_tables,
            formulas=all_formulas,
        )
        stage_durations["KNOWLEDGE_CHUNKER"] = round((time.time() - t0) * 1000, 2)
        
        # 7.5 Question Paper Extraction
        if document_type == "QUESTION_PAPER":
            t0 = time.time()
            from app.pipeline.question_extractor import QuestionPaperExtractor
            extracted_qs = QuestionPaperExtractor.extract_questions(
                session=session,
                doc_id=doc_id,
                pages_data=pages_data
            )
            stage_durations["QUESTION_EXTRACTION"] = round((time.time() - t0) * 1000, 2)

        # 8. Semantic Knowledge Relationships (Graph)
        t0 = time.time()
        relationships = []
        # Link adjacent and conceptually overlapping chunks
        for i in range(len(chunks) - 1):
            chunk_a = chunks[i]
            chunk_b = chunks[i + 1]
            rels = SemanticKnowledgeExtractor.infer_relationships(
                chunk_a_id=chunk_a["id"],
                chunk_a_meta=chunk_a,
                chunk_b_id=chunk_b["id"],
                chunk_b_meta=chunk_b,
            )
            relationships.extend(rels)
        stage_durations["SEMANTIC_GRAPH"] = round((time.time() - t0) * 1000, 2)

        # 9. Quality Validation
        t0 = time.time()
        valid_chunks, valid_rels, val_metrics = QualityValidator.validate_chunks(chunks, relationships)
        stage_durations["QUALITY_VALIDATOR"] = round((time.time() - t0) * 1000, 2)

        # 10. Canonical Document Representation Assembly
        t0 = time.time()
        meta_dict["status"] = "INDEXED"
        meta_dict["current_stage"] = "COMPLETED"
        canonical_doc = CanonicalDocumentBuilder.assemble_canonical(
            doc_metadata=meta_dict,
            pages_data=pages_data,
            structure_tree=structure_tree,
            chunks=valid_chunks,
            tables=all_tables,
            formulas=all_formulas,
            relationships=valid_rels,
        )
        stage_durations["CANONICAL_SYNTHESIS"] = round((time.time() - t0) * 1000, 2)

        # 11. Data Storage Pipeline: Persist to PostgreSQL / pgvector
        t0 = time.time()
        DataStoragePipeline.persist_canonical_document(
            session=session,
            canonical_doc=canonical_doc,
            stage_durations=stage_durations,
        )
        stage_durations["DATA_STORAGE_PIPELINE"] = round((time.time() - t0) * 1000, 2)

        total_duration_ms = round((time.time() - start_time) * 1000, 2)
        logger.info(
            f"[DocumentPipelineOrchestrator] Completed processing for {filename} (ID: {doc_id}) "
            f"in {total_duration_ms}ms: {len(valid_chunks)} chunks, {len(all_tables)} tables, "
            f"{len(all_formulas)} formulas, {len(valid_rels)} graph relationships."
        )

        return canonical_doc

    @classmethod
    def process_document_background(
        cls,
        doc_id: str,
        file_bytes: bytes,
        filename: str,
        document_type: str = "STUDY_MATERIAL"
    ):
        """
        Executes the deep parallel pipeline (tables, formulas, 14-dimension chunks,
        graph relationships) in the background without blocking the user.
        """
        from app.core.database import SessionLocal
        db = SessionLocal()
        try:
            logger.info(f"[BackgroundPipeline] Starting parallel deep processing for {filename} (ID: {doc_id})...")
            cls.process_document(
                session=db,
                file_bytes=file_bytes,
                filename=filename,
                existing_doc_id=doc_id,
                document_type=document_type
            )
            logger.info(f"[BackgroundPipeline] Completed deep processing for {filename} (ID: {doc_id}).")

            # Post-Processing: LLM-Decided Important Topics Synthesis & Interactive Overview
            try:
                from app.models.session import StudySession, CurriculumTopic, ChatMessage
                from app.models.chunk import KnowledgeChunk
                from app.tutoring.curriculum.synthesizer import CurriculumSynthesizer
                import uuid

                db_chunks = db.query(KnowledgeChunk).filter(KnowledgeChunk.document_id == doc_id).limit(20).all()
                chunks_sample = [
                    {"content": c.content, "search_text": c.search_text, "topic": c.topic, "page_number": c.page_number}
                    for c in db_chunks
                ]
                db_doc = db.query(Document).filter(Document.id == doc_id).first()
                doc_title = db_doc.title or filename if db_doc else filename

                sessions = db.query(StudySession).filter(StudySession.document_id == doc_id).all()
                existing_toc = [t.title for s in sessions for t in s.curriculum_topics]

                synthesis = CurriculumSynthesizer.synthesize_curriculum(
                    document_title=doc_title,
                    chunks_sample=chunks_sample,
                    existing_toc=existing_toc
                )

                for sess in sessions:
                    important_topics = synthesis.get("important_topics", [])
                    if important_topics:
                        db.query(CurriculumTopic).filter(CurriculumTopic.session_id == sess.id).delete(synchronize_session=False)
                        for t_data in important_topics:
                            new_top = CurriculumTopic(
                                session_id=sess.id,
                                document_id=doc_id,
                                title=t_data.get("title", "Core Topic"),
                                summary=t_data.get("summary", ""),
                                difficulty=t_data.get("difficulty", "Intermediate"),
                                estimated_study_time=t_data.get("estimated_study_time", "20 mins"),
                                order_index=t_data.get("order", 0),
                                key_concepts=t_data.get("key_concepts", []),
                                page_start=1,
                                page_end=db_doc.page_count if db_doc else 1
                            )
                            db.add(new_top)
                        sess.topic_count = len(important_topics)

                    # Persist opening LLM overview message if no overview message exists
                    existing_msg = db.query(ChatMessage).filter(
                        ChatMessage.session_id == sess.id,
                        ChatMessage.intent == "DOCUMENT_OVERVIEW"
                    ).first()
                    if not existing_msg:
                        briefing_text = synthesis.get("welcome_briefing_markdown") or (
                            f"### 📚 Important Topics in **{doc_title}**\n\n"
                            + "\n".join([f"- **{t['title']}**: {t['summary']}" for t in important_topics])
                        )
                        suggested_qs = [t["suggested_question"] for t in important_topics if t.get("suggested_question")]
                        overview_msg = ChatMessage(
                            id=f"msg-overview-{uuid.uuid4().hex[:8]}",
                            session_id=sess.id,
                            role="assistant",
                            content=briefing_text,
                            intent="DOCUMENT_OVERVIEW",
                            grounding_score=1.0,
                            citations=[]
                        )
                        db.add(overview_msg)
                        sess.message_count = (sess.message_count or 0) + 1

                db.commit()
                logger.info(f"[BackgroundPipeline] Synthesized and saved {len(important_topics)} LLM important topics for {filename}.")
            except Exception as synth_err:
                logger.warning(f"[BackgroundPipeline] Topic synthesis failed: {synth_err}")
        except Exception as e:
            logger.error(f"[BackgroundPipeline] Deep processing failed for {filename}: {e}", exc_info=True)
            db_doc = db.query(Document).filter(Document.id == doc_id).first()
            if db_doc:
                db_doc.status = "INDEXED"
                db.commit()
        finally:
            db.close()
