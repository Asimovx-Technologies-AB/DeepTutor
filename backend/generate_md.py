from app.rag.document_processor import process_pdf
from pathlib import Path

pdf_path = "uploads/72a51c76-470e-498b-8516-f6aac70c9132/828ccdae-ba17-497f-b417-5239d5d2608b/ml algorithams.pdf"
chunks = process_pdf(pdf_path)

lines = ["# Document Export: ML Algorithms\n"]
for c in chunks:
    page = c.get("metadata", {}).get("page", "?")
    sec = c.get("metadata", {}).get("section_title", "")
    header = f"## Page {page}" + (f" — {sec}" if sec else "")
    lines.append(header)
    lines.append(c["text"])
    lines.append("")

out_file = Path("docling_exported_document.md")
out_file.write_text("\n".join(lines), encoding="utf-8")
print(f"Exported {len(chunks)} chunks to {out_file.resolve()}")
