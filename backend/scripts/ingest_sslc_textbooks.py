"""
SSLC (10th Grade) Multimodal Textbook Ingestion Script (VLM + Vector Store)
==========================================================================
Extracts:
  - High-fidelity LaTeX mathematical & chemical formulas ($$ / $) via Gemini 2.0 Flash VLM
  - Clean Markdown tables
  - Deep descriptions of diagrams, circuit schematics, ray diagrams & apparatuses
  - Step-by-step solved numerical examples
  - 3072-dimension Gemini embeddings upserted to Pinecone cloud index 'textbook'

Usage:
  python scripts/ingest_sslc_textbooks.py --all
  python scripts/ingest_sslc_textbooks.py --subject sslc-physics
  python scripts/ingest_sslc_textbooks.py --pdf_path <path_to_pdf> --subject sslc-physics --topic_id phys-10-3
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
# Curriculum Taxonomy & Configuration
# ══════════════════════════════════════════════════════════════════════════════

CURRICULUM_CATALOG = {
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

VLM_PROMPT = """You are an expert academic STEM textbook transcription engine. 
Transcribe the provided textbook page faithfully into clean, structured Markdown:
1. Format structure cleanly with # headings, ## subheadings, and bullet lists.
2. Convert all mathematical equations and chemical formulas into clean LaTeX ($...$ inline, $$...$$ block).
3. Format all tables as clean Markdown tables.
4. For all diagrams, ray diagrams, circuit schematics, apparatuses, and graphs, insert:
   [Figure: <detailed pedagogical description including labels, ray directions, axes, components, and concepts>]
5. Keep solved numerical examples clear with Given, Formula, Steps, and Final Answer.
6. Transcribe faithfully without summarizing or omitting text.
"""

FORMULA_REGEX = [
    re.compile(r'\$\$.+?\$\$', re.DOTALL),
    re.compile(r'\$.+?\$'),
    re.compile(r'(?:[A-Za-z_]+\s*=\s*[-+]?[0-9a-zA-Z_\s\+\-\*/\(\)\^\\\{\}\.]+)', re.MULTILINE),
]


class SSLCTextbookParser:
    def __init__(self, concurrency: int = 5, dpi: int = 150):
        self.embedder = embedding_pipeline
        self.concurrency = concurrency
        self.dpi = dpi
        self._semaphore: Optional[asyncio.Semaphore] = None

    def _get_semaphore(self) -> asyncio.Semaphore:
        if self._semaphore is None:
            self._semaphore = asyncio.Semaphore(self.concurrency)
        return self._semaphore

    def render_page_to_png_bytes(self, doc: fitz.Document, page_num: int) -> bytes:
        """Render a 1-indexed PDF page to PNG bytes."""
        page = doc.load_page(page_num - 1)
        matrix = fitz.Matrix(self.dpi / 72, self.dpi / 72)
        pix = page.get_pixmap(matrix=matrix, alpha=False)
        return pix.tobytes("png")

    async def transcribe_page_vlm(self, doc: fitz.Document, page_num: int, subject_name: str) -> Dict[str, Any]:
        """Transcribe a page using Gemini 2.0 Flash VLM with persistent disk caching."""
        async with self._get_semaphore():
            img_bytes = self.render_page_to_png_bytes(doc, page_num)
            
            # Check local disk cache first (zero cost)
            cached_text = vlm_cache.get(img_bytes)
            if cached_text:
                return {"page": page_num, "text": cached_text, "cached": True}

            # Call Gemini VLM
            target_model = getattr(settings, "GEMINI_VLM_MODEL", "gemini-2.0-flash") or "gemini-2.0-flash"
            try:
                text = await gemini.transcribe_image_vlm(
                    img_bytes,
                    prompt=VLM_PROMPT,
                    mime_type="image/png",
                    model=target_model
                )
                if text and text.strip():
                    vlm_cache.set(img_bytes, text.strip(), metadata={"page": page_num, "subject": subject_name})
                    return {"page": page_num, "text": text.strip(), "cached": False}
            except Exception as e:
                print(f"⚠️ [VLM Note] Page {page_num} API fallback: {e}")

            # PyMuPDF text fallback
            plain_text = doc.load_page(page_num - 1).get_text("text")
            return {"page": page_num, "text": plain_text.strip(), "cached": False, "fallback": True}

    def create_chunks_from_markdown(
        self,
        page_num: int,
        markdown_text: str,
        subject_id: str,
        topic_id: str,
        chapter_title: str,
        source_name: str
    ) -> List[Dict]:
        """Split VLM Markdown into structured semantic chunks with formula metadata."""
        if not markdown_text or len(markdown_text.strip()) < 20:
            return []

        # Find LaTeX formulas
        formulas = []
        for pat in FORMULA_REGEX:
            for match in pat.finditer(markdown_text):
                f_str = match.group().strip()
                if len(f_str) >= 3 and f_str not in formulas:
                    formulas.append(f_str)

        sections = re.split(r'\n(?=#{1,4}\s)', markdown_text)
        chunks = []

        for sec in sections:
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

    async def ingest_subject_full(self, subject_id: str, config: Dict):
        """Ingest all chapters of an SSLC subject using VLM."""
        pdf_path = config["pdf_path"]
        if not os.path.exists(pdf_path):
            print(f"❌ PDF not found for {config['subject_name']}: {pdf_path}")
            return

        print(f"\n{'='*70}")
        print(f"🚀 INGESTING SUBJECT WITH VLM: {config['subject_name']}")
        print(f"   PDF: {pdf_path}")
        print(f"{'='*70}")

        doc = fitz.open(pdf_path)
        pages_to_process = sorted(list(set(config["subject_pages"])))
        print(f"📄 Target Pages: {len(pages_to_process)} (Pages {min(pages_to_process)}..{max(pages_to_process)})")

        # 1. Transcribe pages concurrently
        print(f"⚡ Transcribing pages via Gemini Flash VLM (Concurrency={self.concurrency})...", flush=True)
        tasks = [
            self.transcribe_page_vlm(doc, p, config["subject_name"])
            for p in pages_to_process
        ]
        transcription_results = await asyncio.gather(*tasks)
        transcriptions_by_page = {r["page"]: r["text"] for r in transcription_results}
        
        cached_n = sum(1 for r in transcription_results if r.get("cached"))
        print(f"✓ Transcriptions complete: {cached_n} cached, {len(transcription_results) - cached_n} API processed.", flush=True)
        doc.close()

        # 2. Ingest per chapter
        all_subject_chunks = []
        for topic_id, chapter_title, ch_pages in config["chapters"]:
            print(f"\n📦 Chapter: {chapter_title} [{topic_id}] (Pages {min(ch_pages)}..{max(ch_pages)})", flush=True)
            ch_chunks = []
            for p in ch_pages:
                p_text = transcriptions_by_page.get(p, "")
                if p_text:
                    p_chunks = self.create_chunks_from_markdown(
                        page_num=p,
                        markdown_text=p_text,
                        subject_id=subject_id,
                        topic_id=topic_id,
                        chapter_title=chapter_title,
                        source_name=Path(pdf_path).name
                    )
                    ch_chunks.extend(p_chunks)

            if not ch_chunks:
                print(f"   ⚠️ No chunks extracted for {topic_id}")
                continue

            print(f"   Computing embeddings for {len(ch_chunks)} chunks...", flush=True)
            texts = [c["text"] for c in ch_chunks]
            embeddings = await self.embedder.embed_batch(texts)

            try:
                active_vector_store.delete_topic(topic_id)
            except Exception:
                pass

            active_vector_store.add_chunks(
                topic_id=topic_id,
                chunks=ch_chunks,
                embeddings=embeddings
            )
            print(f"   ✅ Indexed {len(ch_chunks)} vectors to Pinecone namespace '{topic_id}'", flush=True)
            all_subject_chunks.extend(ch_chunks)

        # 3. Whole subject index
        if all_subject_chunks:
            print(f"\n🌐 Indexing whole subject collection '{subject_id}' ({len(all_subject_chunks)} chunks)...", flush=True)
            sub_texts = [c["text"] for c in all_subject_chunks]
            sub_embeddings = await self.embedder.embed_batch(sub_texts)

            try:
                active_vector_store.delete_topic(subject_id)
            except Exception:
                pass

            active_vector_store.add_chunks(
                topic_id=subject_id,
                chunks=all_subject_chunks,
                embeddings=sub_embeddings
            )
            print(f"✅ Ingested {len(all_subject_chunks)} vectors to Pinecone subject namespace '{subject_id}'\n", flush=True)


    async def ingest_single_file(self, pdf_path: str, subject_id: str, topic_id: str, page_numbers: Optional[List[int]] = None):
        """Ingest an arbitrary PDF file using VLM into Pinecone."""
        file_p = Path(pdf_path)
        if not file_p.exists():
            print(f"❌ Error: File not found: {pdf_path}")
            return

        doc = fitz.open(str(file_p))
        total_pages = len(doc)
        pages_to_process = page_numbers if page_numbers else list(range(1, total_pages + 1))

        print(f"\n📘 Processing PDF: {file_p.name} with Gemini VLM")
        print(f"   Subject: {subject_id} | Topic ID: {topic_id} | Pages: {len(pages_to_process)}")

        tasks = [
            self.transcribe_page_vlm(doc, p, subject_id)
            for p in pages_to_process
        ]
        transcription_results = await asyncio.gather(*tasks)
        doc.close()

        all_chunks = []
        for r in transcription_results:
            p_chunks = self.create_chunks_from_markdown(
                page_num=r["page"],
                markdown_text=r["text"],
                subject_id=subject_id,
                topic_id=topic_id,
                chapter_title=topic_id,
                source_name=file_p.name
            )
            all_chunks.extend(p_chunks)

        print(f"✓ Generated {len(all_chunks)} VLM chunks. Computing embeddings...", flush=True)
        texts = [c["text"] for c in all_chunks]
        embeddings = await self.embedder.embed_batch(texts)

        try:
            active_vector_store.delete_topic(topic_id)
        except Exception:
            pass

        active_vector_store.add_chunks(
            topic_id=topic_id,
            chunks=all_chunks,
            embeddings=embeddings
        )
        print(f"🎉 Successfully indexed {len(all_chunks)} chunks into Pinecone under topic '{topic_id}'!\n", flush=True)


# ══════════════════════════════════════════════════════════════════════════════
# CLI Entry Point
# ══════════════════════════════════════════════════════════════════════════════

async def async_main():
    parser = argparse.ArgumentParser(description="Ingest 10th Class SSLC Textbooks into Pinecone 'textbook' index using Gemini VLM")
    parser.add_argument("--all", action="store_true", help="Ingest all 3 curriculum textbooks (Physics, Chemistry, Math)")
    parser.add_argument("--subject", type=str, choices=["sslc-physics", "sslc-chemistry", "sslc-math"], help="Ingest a specific subject")
    parser.add_argument("--pdf_path", type=str, help="Custom PDF file path")
    parser.add_argument("--topic_id", type=str, default="sslc-general", help="Topic ID for custom PDF")
    parser.add_argument("--concurrency", type=int, default=5, help="Concurrent Gemini VLM requests")

    args = parser.parse_args()
    parser_inst = SSLCTextbookParser(concurrency=args.concurrency)

    if args.all:
        for subj, config in CURRICULUM_CATALOG.items():
            await parser_inst.ingest_subject_full(subj, config)
    elif args.subject:
        config = CURRICULUM_CATALOG[args.subject]
        await parser_inst.ingest_subject_full(args.subject, config)
    elif args.pdf_path:
        subj = args.subject or "sslc-custom"
        await parser_inst.ingest_single_file(args.pdf_path, subj, args.topic_id)
    else:
        print("💡 How to use ingest_sslc_textbooks.py:")
        print("  1. Ingest all 3 textbooks:  python scripts/ingest_sslc_textbooks.py --all")
        print("  2. Ingest Physics:          python scripts/ingest_sslc_textbooks.py --subject sslc-physics")
        print("  3. Ingest Chemistry:        python scripts/ingest_sslc_textbooks.py --subject sslc-chemistry")
        print("  4. Ingest Mathematics:      python scripts/ingest_sslc_textbooks.py --subject sslc-math")
        print("  5. Ingest custom PDF:       python scripts/ingest_sslc_textbooks.py --pdf_path <file.pdf> --topic_id my-topic")


if __name__ == "__main__":
    asyncio.run(async_main())
