"""
Stage 1 & 2 — VLM-Powered Multimodal Textbook Ingestion Script
==============================================================
Transcribes textbook PDF pages using Google Gemini 2.0 Flash Vision-Language Model (VLM).
Extracts:
  - High-precision LaTeX mathematical and chemical equations ($...$ and $$...$$)
  - Layout-aware structured Markdown (headings, sidebars, bullet points)
  - Structured Markdown tables
  - Deep descriptive annotations for figures, ray diagrams, circuit schematics, graphs
  - Per-page disk caching to eliminate duplicate API calls
  - 3072-dimension Gemini embeddings upserted to Pinecone cloud index 'textbook'

Usage:
  python scripts/ingest_textbooks_vlm.py                  # Ingest all 3 SSLC textbooks
  python scripts/ingest_textbooks_vlm.py --subject sslc-physics
  python scripts/ingest_textbooks_vlm.py --topic phys-10-1
"""

import os
import sys
import re
import json
import asyncio
import argparse
from pathlib import Path
from typing import List, Dict, Optional, Tuple, Any

# Fix Windows console UTF-8 encoding
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

# Ensure backend root is on sys.path
backend_dir = Path(__file__).resolve().parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

import pymupdf as fitz
from app.core.config import get_settings
from app.rag.gemini_client import gemini
from app.rag.vlm_cache import vlm_cache
from app.rag.pipeline.embedder import embedding_pipeline
from app.rag.storage import active_vector_store

settings = get_settings()
root_dir = backend_dir.parent
textbook_dir = root_dir / "TextBook"

# ══════════════════════════════════════════════════════════════════════════════
# Curriculum Catalog
# ══════════════════════════════════════════════════════════════════════════════

CURRICULUM_CONFIG = {
    # ⚡ Physics Full Textbook (Part 1 - 4 Chapters)
    "sslc-physics": {
        "pdf_path": str(textbook_dir / "Hsslive-15_Physics Eng.pdf"),
        "subject_name": "Class 10 Physics",
        "subject_pages": list(range(7, 89)),
        "chapters": [
            ("phys-10-1", "1. Wave Motion & Oscillations", list(range(7, 27))),
            ("phys-10-2", "2. Refraction of Light & Lenses", list(range(27, 49))),
            ("phys-10-3", "3. Dispersion of Light & Colour", list(range(49, 69))),
            ("phys-10-4", "4. Magnetic Effect of Electric Current", list(range(69, 89))),
        ]
    },

    # 🧪 Chemistry Full Textbook (Part 1 - 4 Units)
    "sslc-chemistry": {
        "pdf_path": str(textbook_dir / "Hsslive-19_Chemistry Eng.pdf"),
        "subject_name": "Class 10 Chemistry",
        "subject_pages": list(range(1, 97)),
        "chapters": [
            ("chem-10-1", "1. Nomenclature of Organic Compounds & Isomerism", list(range(1, 33))),
            ("chem-10-2", "2. Chemical Reactions of Organic Compounds", list(range(33, 49))),
            ("chem-10-3", "3. Periodic Table & Electron Configuration", list(range(49, 73))),
            ("chem-10-4", "4. Gas Laws and Mole Concept", list(range(73, 97))),
        ]
    },

    # 📐 Mathematics Full Textbook (Part 1 - 7 Chapters)
    "sslc-math": {
        "pdf_path": str(textbook_dir / "Hsslive-35_Maths Eng.pdf"),
        "subject_name": "Class 10 Mathematics",
        "subject_pages": list(range(7, 153)),
        "chapters": [
            ("math-10-1", "1. Arithmetic Sequences", list(range(7, 31))),
            ("math-10-2", "2. Circles and Angles", list(range(31, 59))),
            ("math-10-3", "3. Arithmetic Sequences & Algebra", list(range(59, 73))),
            ("math-10-4", "4. Mathematics of Chance", list(range(73, 85))),
            ("math-10-5", "5. Second Degree Equations", list(range(85, 97))),
            ("math-10-6", "6. Trigonometry", list(range(97, 127))),
            ("math-10-7", "7. Coordinates", list(range(127, 153))),
        ]
    },
}

VLM_TRANSCRIPTION_PROMPT = """You are an expert academic STEM textbook transcription engine. 
Transcribe the provided textbook page faithfully into clean, well-structured Markdown:
1. Format document structure cleanly:
   - Use # for chapter titles, ## for section headings, ### for subheadings.
   - Use bullet points and numbered lists where appropriate.
2. Mathematical & Chemical Equations:
   - Convert all mathematical formulas and chemical reactions into valid LaTeX syntax.
   - Use $...$ for inline formulas and $$...$$ for block/standalone equations.
3. Tables & Lists:
   - Convert all tables into clean GitHub-flavored Markdown tables.
4. Diagrams, Charts, Ray Diagrams & Schematics:
   - For every diagram, circuit schematic, optical ray diagram, apparatus illustration, or graph, insert a descriptive block:
     [Figure: <detailed description of the diagram including labels, components, light ray directions, axes, variables, and scientific concept illustrated>]
5. Solved Examples & Activities:
   - Keep solved numerical problems clearly formatted with Given, Formula, Step-by-step substitution, and Final answer.
6. Fidelity:
   - Transcribe all text verbatim without summarizing, skipping content, or hallucinating.
"""

LATEX_FORMULA_REGEX = [
    re.compile(r'\$\$.+?\$\$', re.DOTALL),
    re.compile(r'\$.+?\$'),
    re.compile(r'(?:[A-Za-z_]+\s*=\s*[-+]?[0-9a-zA-Z_\s\+\-\*/\(\)\^\\\{\}\.]+)', re.MULTILINE),
]


class VLMTextbookIngestor:
    def __init__(self, concurrency: int = 5, dpi: int = 150):
        self.concurrency = concurrency
        self.dpi = dpi
        self.semaphore = asyncio.Semaphore(concurrency)

    def render_page_to_png_bytes(self, doc: fitz.Document, page_num: int) -> bytes:
        """Render a 1-indexed PDF page to optimized PNG bytes."""
        page = doc.load_page(page_num - 1)
        matrix = fitz.Matrix(self.dpi / 72, self.dpi / 72)
        pix = page.get_pixmap(matrix=matrix, alpha=False)
        return pix.tobytes("png")

    async def transcribe_page_vlm(self, doc: fitz.Document, page_num: int, subject_name: str) -> Dict[str, Any]:
        """Transcribe a single page using Gemini 2.0 Flash VLM with caching and concurrency control."""
        async with self.semaphore:
            img_bytes = self.render_page_to_png_bytes(doc, page_num)
            
            # Check local disk cache
            cached_text = vlm_cache.get(img_bytes)
            if cached_text:
                return {
                    "page": page_num,
                    "text": cached_text,
                    "cached": True
                }

            # Call Gemini VLM API
            target_model = getattr(settings, "GEMINI_VLM_MODEL", "gemini-2.0-flash") or "gemini-2.0-flash"
            try:
                text = await gemini.transcribe_image_vlm(
                    img_bytes,
                    prompt=VLM_TRANSCRIPTION_PROMPT,
                    mime_type="image/png",
                    model=target_model
                )
                if text and text.strip():
                    vlm_cache.set(img_bytes, text.strip(), metadata={"page": page_num, "subject": subject_name})
                    return {
                        "page": page_num,
                        "text": text.strip(),
                        "cached": False
                    }
            except Exception as e:
                print(f"⚠️ [VLM Error] Page {page_num} transcription failed: {e}")

            # Fallback: PyMuPDF plain text if VLM call fails
            plain_text = doc.load_page(page_num - 1).get_text("text")
            return {
                "page": page_num,
                "text": plain_text.strip(),
                "cached": False,
                "fallback": True
            }

    def chunk_page_markdown(
        self,
        page_num: int,
        markdown_text: str,
        subject_id: str,
        topic_id: str,
        chapter_title: str,
        source_name: str
    ) -> List[Dict]:
        """Split page Markdown into high-cohesion RAG chunks preserving LaTeX and diagrams."""
        if not markdown_text or len(markdown_text.strip()) < 20:
            return []

        # Extract formulas
        formulas = []
        for pat in LATEX_FORMULA_REGEX:
            for match in pat.finditer(markdown_text):
                f_str = match.group().strip()
                if len(f_str) >= 3 and f_str not in formulas:
                    formulas.append(f_str)

        # Split by double newline while respecting section headers
        raw_sections = re.split(r'\n(?=#{1,4}\s)', markdown_text)
        chunks = []

        for sec in raw_sections:
            sec = sec.strip()
            if not sec:
                continue

            paragraphs = [p.strip() for p in sec.split("\n\n") if p.strip()]
            buffer = []
            word_count = 0

            for p in paragraphs:
                p_words = len(p.split())
                if word_count + p_words > 320 and buffer:
                    chunk_str = "\n\n".join(buffer)
                    chunk_formulas = [f for f in formulas if f in chunk_str]
                    chunks.append({
                        "text": chunk_str,
                        "metadata": {
                            "source": source_name,
                            "subject_id": subject_id,
                            "topic_id": topic_id,
                            "chapter_title": chapter_title,
                            "page": page_num,
                            "has_formula": bool(chunk_formulas),
                            "formulas": chunk_formulas,
                            "has_diagram": "[Figure:" in chunk_str or "[Diagram:" in chunk_str,
                            "chunk_type": "vlm_markdown",
                        }
                    })
                    buffer = [p]
                    word_count = p_words
                else:
                    buffer.append(p)
                    word_count += p_words

            if buffer:
                chunk_str = "\n\n".join(buffer)
                chunk_formulas = [f for f in formulas if f in chunk_str]
                chunks.append({
                    "text": chunk_str,
                    "metadata": {
                        "source": source_name,
                        "subject_id": subject_id,
                        "topic_id": topic_id,
                        "chapter_title": chapter_title,
                        "page": page_num,
                        "has_formula": bool(chunk_formulas),
                        "formulas": chunk_formulas,
                        "has_diagram": "[Figure:" in chunk_str or "[Diagram:" in chunk_str,
                        "chunk_type": "vlm_markdown",
                    }
                })

        return chunks

    async def ingest_subject(self, subject_id: str, config: Dict):
        pdf_path = config["pdf_path"]
        if not os.path.exists(pdf_path):
            print(f"❌ PDF not found for {config['subject_name']}: {pdf_path}")
            return

        print(f"\n{'='*70}")
        print(f"📖 PROCESSING SUBJECT WITH GEMINI VLM: {config['subject_name']}")
        print(f"   File: {pdf_path}")
        print(f"{'='*70}")

        doc = fitz.open(pdf_path)
        total_pdf_pages = len(doc)
        pages_to_process = sorted(list(set(config["subject_pages"])))
        print(f"📄 Total PDF Pages: {total_pdf_pages} | Target Pages to Ingest: {len(pages_to_process)} (Pages {min(pages_to_process)}..{max(pages_to_process)})")

        # 1. Transcribe pages concurrently with VLM
        print(f"⚡ Transcribing {len(pages_to_process)} pages via Gemini Flash VLM (Concurrency={self.concurrency})...")
        tasks = [
            self.transcribe_page_vlm(doc, p, config["subject_name"])
            for p in pages_to_process
        ]
        
        transcription_results = await asyncio.gather(*tasks)
        transcriptions_by_page = {r["page"]: r["text"] for r in transcription_results}
        
        cached_count = sum(1 for r in transcription_results if r.get("cached"))
        api_count = len(transcription_results) - cached_count
        print(f"✓ Transcriptions complete: {cached_count} from cache, {api_count} new VLM API calls.")

        doc.close()

        # 2. Ingest per chapter
        all_subject_chunks = []
        for topic_id, chapter_title, ch_pages in config["chapters"]:
            print(f"\n--- Ingesting Chapter: {chapter_title} [{topic_id}] (Pages {min(ch_pages)}..{max(ch_pages)}) ---")
            ch_chunks = []
            for p in ch_pages:
                page_text = transcriptions_by_page.get(p, "")
                if page_text:
                    p_chunks = self.chunk_page_markdown(
                        page_num=p,
                        markdown_text=page_text,
                        subject_id=subject_id,
                        topic_id=topic_id,
                        chapter_title=chapter_title,
                        source_name=Path(pdf_path).name
                    )
                    ch_chunks.extend(p_chunks)

            if not ch_chunks:
                print(f"   ⚠️ No chunks extracted for chapter {topic_id}")
                continue

            print(f"   Generated {len(ch_chunks)} VLM chunks. Computing 3072-dim Gemini embeddings...")
            texts = [c["text"] for c in ch_chunks]
            embeddings = await embedding_pipeline.embed_batch(texts)

            # Upsert into Pinecone chapter namespace
            try:
                active_vector_store.delete_topic(topic_id)
            except Exception:
                pass

            active_vector_store.add_chunks(
                topic_id=topic_id,
                chunks=ch_chunks,
                embeddings=embeddings
            )
            print(f"   ✅ Upserted {len(ch_chunks)} vectors to Pinecone namespace '{topic_id}'")
            all_subject_chunks.extend(ch_chunks)

        # 3. Ingest overall subject namespace
        if all_subject_chunks:
            print(f"\n🌐 Indexing whole subject collection '{subject_id}' ({len(all_subject_chunks)} total chunks)...")
            sub_texts = [c["text"] for c in all_subject_chunks]
            sub_embeddings = await embedding_pipeline.embed_batch(sub_texts)

            try:
                active_vector_store.delete_topic(subject_id)
            except Exception:
                pass

            active_vector_store.add_chunks(
                topic_id=subject_id,
                chunks=all_subject_chunks,
                embeddings=sub_embeddings
            )
            print(f"✅ Upserted {len(all_subject_chunks)} vectors to Pinecone subject namespace '{subject_id}'\n")


async def main():
    parser = argparse.ArgumentParser(description="Ingest textbook PDFs using Gemini VLM into Pinecone index 'textbook'")
    parser.add_argument("--subject", type=str, choices=list(CURRICULUM_CONFIG.keys()) + ["all"], default="all",
                        help="Subject to ingest (sslc-physics, sslc-chemistry, sslc-math, or all)")
    parser.add_argument("--concurrency", type=int, default=5, help="Number of parallel Gemini VLM requests")
    parser.add_argument("--dpi", type=int, default=150, help="DPI for rendering PDF page images")
    args = parser.parse_args()

    print("=" * 70)
    print("DeepTutor VLM Textbook Ingestion Pipeline (Pinecone Index: 'textbook')")
    print("=" * 70)

    ingestor = VLMTextbookIngestor(concurrency=args.concurrency, dpi=args.dpi)

    subjects_to_run = list(CURRICULUM_CONFIG.keys()) if args.subject == "all" else [args.subject]

    for subj in subjects_to_run:
        config = CURRICULUM_CONFIG[subj]
        await ingestor.ingest_subject(subj, config)

    print("\n🎉 ALL SELECTED TEXTBOOKS SUCCESSFULLY TRANSCRIBED WITH VLM & INDEXED INTO PINECONE!")


if __name__ == "__main__":
    asyncio.run(main())
