import io
import pytest
import fitz
from PIL import Image, ImageDraw
from app.pipeline.pdf_parser import PyMuPDFParser
from app.pipeline.classifier import DocumentClassifier
from app.pipeline.text_pipeline.vlm_fallback import VLMFallbackExtractor
from app.pipeline.chunker import KnowledgeChunker
from app.schemas.document import StructuralNode


def create_scanned_pdf_bytes(text: str) -> bytes:
    """Creates a PDF consisting strictly of a rasterized image with 0 digital text streams."""
    # 1. Render text onto an image canvas
    img = Image.new("RGB", (600, 300), color=(255, 255, 255))
    draw = ImageDraw.Draw(img)
    draw.text((30, 40), text, fill=(0, 0, 0))

    img_bytes_io = io.BytesIO()
    img.save(img_bytes_io, format="PNG")
    img_data = img_bytes_io.getvalue()

    # 2. Insert image as a single full-page raster in PyMuPDF without any text layer
    doc = fitz.open()
    page = doc.new_page(width=600, height=300)
    page.insert_image(page.rect, stream=img_data)

    pdf_bytes = doc.tobytes()
    doc.close()
    return pdf_bytes


def test_scanned_pdf_vlm_end_to_end():
    """Verify that an image-only scanned PDF renders page images, transcribes via VLM, and produces knowledge chunks."""
    sample_text = "Types of Forest in India: Reserved Forests, Protected Forests, and Unclassed Forests."
    pdf_bytes = create_scanned_pdf_bytes(sample_text)

    # 1. Parse document with PyMuPDFParser
    parser = PyMuPDFParser(render_dpi=150)
    parsed_pages = parser.parse_document(pdf_bytes, doc_id="test_scanned_doc")

    assert len(parsed_pages) == 1
    page = parsed_pages[0]

    # Verify that it has 0 native digital text (it's a scan)
    assert page["raw_text"].strip() == ""
    assert page["char_count"] == 0

    # Verify that the parser automatically rendered the page image
    assert page["image_bytes"] is not None
    assert len(page["image_bytes"]) > 0

    # 2. Document Classifier detects it as scanned
    classification = DocumentClassifier.classify_document(parsed_pages)
    assert classification["overall_classification"] == "scanned"
    page["classification"] = "scanned"

    # 3. VLMFallbackExtractor processes scanned page
    transcribed_md = VLMFallbackExtractor.process_scanned_page(page)

    assert transcribed_md is not None
    assert len(transcribed_md.strip()) > 0
    # Gemini VLM should transcribe the words from the image
    assert any(term in transcribed_md.lower() for term in ["forest", "reserved", "protected", "india"])

    # Verify that synthetic LayoutBlocks were populated
    assert len(page["blocks"]) > 0
    assert page["blocks"][0].text != ""

    # 4. KnowledgeChunker generates valid chunks
    chunks = KnowledgeChunker.generate_chunks(
        doc_id="test_scanned_doc",
        pages_data=[page],
        structure_tree=[],
        tables=[],
        formulas=[],
    )

    assert len(chunks) >= 1
    first_chunk = chunks[0]
    assert first_chunk["document_id"] == "test_scanned_doc"
    assert first_chunk["page_number"] == 1
    assert first_chunk["provenance"]["source"] == "vlm_transcription"
    assert len(first_chunk["content"]) > 0
