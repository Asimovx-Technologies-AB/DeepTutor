import os
import sys
import asyncio
from pathlib import Path
from pinecone import Pinecone

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
from scripts.ingest_sslc_textbooks import SSLCTextbookParser

settings = get_settings()
root_dir = backend_dir.parent
textbook_dir = root_dir / "TextBook"

TEXTBOOK_CURRICULUM = {
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
}


async def ingest_subject_fast(parser: SSLCTextbookParser, subject_id: str, config: dict):
    pdf_path = config["pdf_path"]
    if not os.path.exists(pdf_path):
        print(f"⚠️ Skipping {config['subject_name']}: File not found at '{pdf_path}'")
        return

    print(f"\n=======================================================")
    print(f"🚀 INGESTING FULL SUBJECT (FAST SINGLE-PASS): {config['subject_name']}")
    print(f"   File: {pdf_path}")
    print(f"=======================================================")

    file_p = Path(pdf_path)
    img_dir = backend_dir / "uploads" / subject_id / "images"

    # 1. Single extraction pass for entire PDF
    print("   ⏳ Extracting all pages, text, formulas, and diagrams...")
    all_pages = parser.extract_text_and_tables(str(file_p))
    all_tables = parser.extract_pdf_tables(str(file_p))
    all_images = parser.extract_images_and_diagrams(str(file_p), img_dir)
    print(f"   ✓ Extracted {len(all_pages)} pages, {len(all_tables)} tables, {len(all_images)} diagrams.")

    # 2. Ingest each individual chapter namespace
    all_subject_chunks = []
    for topic_id, title, pages in config["chapters"]:
        page_set = set(pages)
        ch_pages = [p for p in all_pages if p["page"] in page_set]
        ch_tables = [t for t in all_tables if t["page"] in page_set]
        ch_images = [img for img in all_images if img["page"] in page_set]

        ch_chunks = parser.create_chunks(
            ch_pages, ch_tables, ch_images,
            subject_id=subject_id,
            topic_id=topic_id,
            source_name=file_p.name
        )
        print(f"\n⚡ Ingesting Chapter '{title}' [{topic_id}] (Pages {min(pages)}-{max(pages)}: {len(ch_chunks)} chunks)...")

        texts = [c["text"] for c in ch_chunks]
        embeddings = await embedding_pipeline.embed_batch(texts)

        try:
            active_vector_store.delete_topic(topic_id)
        except Exception:
            pass

        active_vector_store.add_chunks(
            topic_id=topic_id,
            chunks=ch_chunks,
            embeddings=embeddings
        )
        all_subject_chunks.extend(ch_chunks)
        print(f"   ✓ Chapter '{topic_id}' indexed with {len(ch_chunks)} vectors.")

    # 3. Ingest overall subject namespace
    print(f"\n🌐 Indexing whole subject collection '{subject_id}' ({len(all_subject_chunks)} chunks)...")
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
    print(f"✅ Finished {config['subject_name']}! ({len(all_subject_chunks)} chunks total in '{subject_id}')\n")


async def main():
    print("=" * 60)
    print("DeepTutor Fast Pinecone Textbook Ingestion (Gemini Embeddings)")
    print("=" * 60)
    parser = SSLCTextbookParser()
    for subject_id, config in TEXTBOOK_CURRICULUM.items():
        await ingest_subject_fast(parser, subject_id, config)
    print("\n🎉 ALL 3 SUBJECTS SUCCESSFULLY INDEXED INTO PINECONE CLOUD INDEX 'textbook'!")


if __name__ == "__main__":
    asyncio.run(main())
