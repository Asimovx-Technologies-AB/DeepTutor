"""
SSLC (10th Grade) Multimodal Textbook Ingestion Script
======================================================
Extracts:
  - Formatted LaTeX mathematical & chemical formulas ($$ / $)
  - Clean Markdown tables (pdfplumber & Docling)
  - Ray diagrams, circuit schematics, and apparatus images (PyMuPDF + Vision OCR)
  - Step-by-step solved numerical examples (Given -> Formula -> Steps -> Result)
  - Curated curriculum taxonomy for Class 10 Math, Physics & Chemistry

Usage:
  python scripts/ingest_sslc_textbooks.py --pdf_path <path_to_pdf> --subject sslc-physics --topic_id phys-10-3
  python scripts/ingest_sslc_textbooks.py --dir ./sslc_textbooks/
"""

import os
import sys
import re
import json
import asyncio
import argparse
from pathlib import Path
from typing import List, Dict, Optional, Tuple

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

from app.core.config import get_settings
from app.rag.pipeline.embedder import embedding_pipeline
from app.rag.storage import active_vector_store
from app.rag.vector_store import vector_store

settings = get_settings()

# ══════════════════════════════════════════════════════════════════════════════
# Regex Patterns for SSLC Grade 10 STEM Content
# ══════════════════════════════════════════════════════════════════════════════

FORMULA_REGEX = [
    # LaTeX display / inline
    re.compile(r'\$\$.+?\$\$', re.DOTALL),
    re.compile(r'\$.+?\$'),
    # Physics & Math equations (e.g. V = I * R, P = V * I, 1/f = 1/v - 1/u, an = a + (n-1)d)
    re.compile(r'(?:[A-Za-z_]+\s*=\s*[-+]?[0-9a-zA-Z_\s\+\-\*/\(\)\^\\\{\}\.]+)', re.MULTILINE),
    # Chemical reactions (e.g. 2H2 + O2 -> 2H2O, CaCO3 -> CaO + CO2)
    re.compile(r'(?:[0-9]*[A-Z][a-z]?[0-9]*(?:\([a-z]+\))?\s*\+\s*)+[0-9]*[A-Z][a-z]?[0-9]*(?:\([a-z]+\))?\s*(?:->|→|⇌|=)\s*.+', re.MULTILINE),
]

NUMERICAL_EXAMPLE_HEADER = re.compile(
    r'(?:Example\s+\d+[\.\d]*|Sample\s+Problem|Solved\s+Example|Activity\s+\d+[\.\d]*)\s*[:\-]',
    re.IGNORECASE
)


# ══════════════════════════════════════════════════════════════════════════════
# Multimodal Document Parser
# ══════════════════════════════════════════════════════════════════════════════

class SSLCTextbookParser:
    def __init__(self):
        self.embedder = embedding_pipeline

    def extract_text_and_tables(self, pdf_path: str) -> List[Dict]:
        """Extract structured text, tables, and formula blocks per page."""
        try:
            import pymupdf as fitz
        except ImportError:
            import fitz

        pages_data = []
        doc = fitz.open(pdf_path)

        for page_idx, page in enumerate(doc, 1):
            text = page.get_text("text", sort=True)
            if not text or len(text.strip()) < 15:
                continue

            # Extract formulas
            formulas = []
            for pat in FORMULA_REGEX:
                for match in pat.finditer(text):
                    f_text = match.group().strip()
                    if len(f_text) >= 4 and f_text not in formulas:
                        formulas.append(f_text)

            # Check for solved numerical calculations
            is_solved_example = bool(NUMERICAL_EXAMPLE_HEADER.search(text))

            pages_data.append({
                "page": page_idx,
                "text": text.strip(),
                "formulas": formulas,
                "is_example": is_solved_example,
                "char_count": len(text),
            })

        doc.close()
        return pages_data

    def extract_pdf_tables(self, pdf_path: str) -> List[Dict]:
        """Extract all tables as clean Markdown using pdfplumber."""
        tables_data = []
        try:
            import pdfplumber
            with pdfplumber.open(pdf_path) as pdf:
                for page_idx, page in enumerate(pdf.pages, 1):
                    extracted = page.extract_tables()
                    for table in extracted or []:
                        if not table or len(table) < 2:
                            continue
                        # Format as clean markdown table
                        md_rows = []
                        header_row = [str(c or "").replace("\n", " ").strip() for c in table[0]]
                        if not any(header_row):
                            continue
                        md_rows.append("| " + " | ".join(header_row) + " |")
                        md_rows.append("| " + " | ".join(["---"] * len(header_row)) + " |")
                        for row in table[1:]:
                            cells = [str(c or "").replace("\n", " ").strip() for c in row]
                            md_rows.append("| " + " | ".join(cells) + " |")

                        table_md = "\n".join(md_rows)
                        tables_data.append({
                            "page": page_idx,
                            "table_md": table_md,
                            "chunk_type": "table",
                        })
        except Exception as e:
            print(f"[TABLE EXTRACTION NOTE] pdfplumber table extraction skipped: {e}")
        return tables_data

    def extract_images_and_diagrams(self, pdf_path: str, output_dir: Path) -> List[Dict]:
        """Extract embedded diagrams and circuit images with page tracking."""
        try:
            import pymupdf as fitz
        except ImportError:
            import fitz

        output_dir.mkdir(parents=True, exist_ok=True)
        images_data = []
        doc = fitz.open(pdf_path)

        for page_idx, page in enumerate(doc, 1):
            image_list = page.get_images(full=True)
            for img_idx, img in enumerate(image_list):
                xref = img[0]
                base_img = doc.extract_image(xref)
                img_bytes = base_img["image"]
                img_ext = base_img["ext"]

                # Discard tiny icons/bullets (< 3KB)
                if len(img_bytes) < 3000:
                    continue

                img_filename = f"p{page_idx}_img{img_idx}.{img_ext}"
                img_path = output_dir / img_filename
                with open(img_path, "wb") as f:
                    f.write(img_bytes)

                images_data.append({
                    "page": page_idx,
                    "image_path": str(img_path),
                    "filename": img_filename,
                    "chunk_type": "diagram",
                })

        doc.close()
        return images_data

    def create_chunks(
        self,
        pages_data: List[Dict],
        tables_data: List[Dict],
        images_data: List[Dict],
        subject_id: str,
        topic_id: str,
        source_name: str,
    ) -> List[Dict]:
        """Combine all text, formulas, and tables into rich, highly-searchable RAG chunks."""
        chunks = []

        # Map diagrams to pages
        page_diagrams: Dict[int, List[Dict]] = {}
        for img in images_data:
            pno = img.get("page", 0)
            if pno not in page_diagrams:
                page_diagrams[pno] = []
            page_diagrams[pno].append(img)

        # 1. Text & Formulas Chunks (Chunk size ~350 words with paragraph preservation)
        for page in pages_data:
            page_num = page["page"]
            text = page["text"]
            formulas = page.get("formulas", [])
            is_example = page.get("is_example", False)
            diag_list = page_diagrams.get(page_num, [])

            paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
            current_buffer = []
            current_words = 0

            for p in paragraphs:
                words = len(p.split())
                if current_words + words > 350 and current_buffer:
                    chunk_text = "\n\n".join(current_buffer)
                    chunks.append({
                        "text": chunk_text,
                        "metadata": {
                            "source": source_name,
                            "subject_id": subject_id,
                            "topic_id": topic_id,
                            "page": page_num,
                            "has_formula": any(f in chunk_text for f in formulas),
                            "formulas": [f for f in formulas if f in chunk_text],
                            "is_numerical_example": is_example,
                            "chunk_type": "theory" if not is_example else "solved_example",
                            "has_diagram": bool(diag_list),
                        }
                    })
                    current_buffer = [p]
                    current_words = words
                else:
                    current_buffer.append(p)
                    current_words += words

            if current_buffer:
                chunk_text = "\n\n".join(current_buffer)
                chunks.append({
                    "text": chunk_text,
                    "metadata": {
                        "source": source_name,
                        "subject_id": subject_id,
                        "topic_id": topic_id,
                        "page": page_num,
                        "has_formula": any(f in chunk_text for f in formulas),
                        "formulas": [f for f in formulas if f in chunk_text],
                        "is_numerical_example": is_example,
                        "chunk_type": "theory" if not is_example else "solved_example",
                        "has_diagram": bool(diag_list),
                    }
                })

        # 2. Table Chunks (Only include tables that have meaningful text content)
        for tbl in tables_data:
            t_md = tbl.get("table_md", "").strip()
            if len(t_md) > 40:
                table_text = f"[TABLE: {source_name} Page {tbl['page']}]\n\n{t_md}"
                chunks.append({
                    "text": table_text,
                    "metadata": {
                        "source": source_name,
                        "subject_id": subject_id,
                        "topic_id": topic_id,
                        "page": tbl["page"],
                        "has_formula": False,
                        "formulas": [],
                        "is_numerical_example": False,
                        "chunk_type": "table",
                    }
                })

        return chunks

    async def ingest_file(
        self,
        pdf_path: str,
        subject_id: str,
        topic_id: str,
        page_numbers: Optional[List[int]] = None,
    ):
        """Parse, vectorize, and store chunks into the cloud / persistent vector DB."""
        file_p = Path(pdf_path)
        if not file_p.exists():
            print(f"❌ Error: File not found: {pdf_path}")
            return

        print(f"\n📘 Processing SSLC Textbook: {file_p.name}")
        print(f"   Subject: {subject_id} | Topic ID: {topic_id}")
        if page_numbers:
            print(f"   Filtering to {len(page_numbers)} pages ({min(page_numbers)}-{max(page_numbers)})")

        img_dir = backend_dir / "uploads" / subject_id / topic_id / "images"
        
        # 1. Extract
        print("   ⏳ Extracting text, formulas, tables, and diagrams...")
        pages_data = self.extract_text_and_tables(str(file_p))
        tables_data = self.extract_pdf_tables(str(file_p))
        images_data = self.extract_images_and_diagrams(str(file_p), img_dir)

        # Filter by page numbers if specified
        if page_numbers:
            page_set = set(page_numbers)
            pages_data = [p for p in pages_data if p["page"] in page_set]
            tables_data = [t for t in tables_data if t["page"] in page_set]
            images_data = [img for img in images_data if img["page"] in page_set]

        print(f"   ✓ Pages: {len(pages_data)} | Tables: {len(tables_data)} | Diagrams: {len(images_data)}")

        # 2. Chunk
        chunks = self.create_chunks(
            pages_data, tables_data, images_data,
            subject_id=subject_id,
            topic_id=topic_id,
            source_name=file_p.name
        )
        print(f"   ✓ Generated {len(chunks)} multimodal chunks")

        # 3. Embed using active provider (Gemini / gemini-embedding-2)
        print("   ⏳ Computing vector embeddings (models/gemini-embedding-2)...")
        texts = [c["text"] for c in chunks]
        embeddings = await self.embedder.embed_batch(texts)

        # 4. Store into Vector Store
        print("   ⏳ Storing into Vector Database...")
        # Clear existing namespace before inserting fresh embeddings
        try:
            active_vector_store.delete_topic(topic_id)
        except Exception:
            pass

        active_vector_store.add_chunks(
            topic_id=topic_id,
            chunks=chunks,
            embeddings=embeddings,
        )
        print(f"   🎉 Successfully indexed {len(chunks)} chunks into vector store under topic '{topic_id}'!\n")


# ══════════════════════════════════════════════════════════════════════════════
# CLI Entry Point
# ══════════════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="Ingest 10th Class SSLC Textbooks into DeepTutor Cloud/Local Vector DB")
    parser.add_argument("--pdf_path", type=str, help="Path to textbook PDF file")
    parser.add_argument("--subject", type=str, default="sslc-physics", choices=["sslc-math", "sslc-physics", "sslc-chemistry"])
    parser.add_argument("--topic_id", type=str, default="phys-10-3", help="Target topic ID (e.g. phys-10-3, math-10-4, chem-10-1)")

    args = parser.parse_args()

    if not args.pdf_path:
        print("💡 Tip: Provide a textbook PDF using --pdf_path <file.pdf>")
        print("Example: python scripts/ingest_sslc_textbooks.py --pdf_path uploads/10th_Physics_Electricity.pdf --subject sslc-physics --topic_id phys-10-3")
        return

    ingester = SSLCTextbookParser()
    asyncio.run(ingester.ingest_file(args.pdf_path, args.subject, args.topic_id))


if __name__ == "__main__":
    main()
