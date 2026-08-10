"""
Docling PDF to Markdown Exporter
Converts any uploaded PDF into a structured .md Markdown document using IBM Docling or fast fallback parsers.
"""
import sys
import time
from pathlib import Path

# Add backend directory to sys.path
sys.path.insert(0, str(Path(__file__).parent))

from app.rag.document_processor import process_pdf, _get_docling_converter

def convert_pdf_to_markdown(pdf_path: str, output_md_path: str = None) -> str:
    pdf_path = Path(pdf_path)
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF file not found at {pdf_path}")

    if output_md_path is None:
        output_md_path = pdf_path.with_suffix(".md")
    else:
        output_md_path = Path(output_md_path)

    print(f"[EXPORTER] Processing PDF: {pdf_path.name}...")
    t0 = time.time()
    
    # Try Docling direct export if available
    converter = _get_docling_converter()
    if converter is not None:
        try:
            print(f"[DOCLING] Converting with IBM Docling...")
            result = converter.convert(str(pdf_path))
            md_content = result.document.export_to_markdown()
        except Exception as e:
            print(f"[WARN] Docling conversion failed/timed out ({e}). Falling back to text parser...")
            chunks = process_pdf(str(pdf_path))
            md_content = f"# {pdf_path.name}\n\n" + "\n\n".join([c["text"] for c in chunks])
    else:
        chunks = process_pdf(str(pdf_path))
        md_content = f"# {pdf_path.name}\n\n" + "\n\n".join([c["text"] for c in chunks])

    output_md_path.write_text(md_content, encoding="utf-8")
    elapsed = round(time.time() - t0, 2)
    print(f"[SUCCESS] Export complete in {elapsed}s!")
    print(f"[OUTPUT] Saved Markdown file to: {output_md_path.resolve()}")
    return md_content

if __name__ == "__main__":
    import glob
    pdfs = glob.glob("uploads/**/*.pdf", recursive=True)
    if pdfs:
        target_pdf = pdfs[0]
        print(f"Found PDF: {target_pdf}")
        convert_pdf_to_markdown(target_pdf, "exported_document.md")
    else:
        print("Usage: python export_docling_markdown.py <path_to_pdf>")
