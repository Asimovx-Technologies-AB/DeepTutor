import hashlib
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional
import fitz  # PyMuPDF


class MetadataExtractor:
    """Stage 1: Extract file fingerprint, byte size, and PDF trailer metadata."""

    @staticmethod
    def extract_file_hash(file_bytes: bytes) -> str:
        return hashlib.sha256(file_bytes).hexdigest()

    @classmethod
    def extract_pdf_metadata(cls, file_bytes: bytes, filename: str) -> Dict[str, Any]:
        file_hash = cls.extract_file_hash(file_bytes)
        file_size = len(file_bytes)

        metadata: Dict[str, Any] = {
            "file_hash": file_hash,
            "filename": filename,
            "file_size_bytes": file_size,
            "mime_type": "application/pdf",
            "page_count": 0,
            "title": None,
            "author": None,
            "creation_date": None,
            "pdf_version": None,
            "is_encrypted": False,
        }

        try:
            doc = fitz.open(stream=file_bytes, filetype="pdf")
            metadata["page_count"] = len(doc)
            metadata["is_encrypted"] = doc.is_encrypted

            pdf_meta = doc.metadata or {}
            raw_title = (pdf_meta.get("title") or "").strip()
            # Reject raw_title if empty or if it represents an authoring file path / source file (.pmd, .indd, etc.)
            is_path_or_source = (
                not raw_title
                or "\\" in raw_title
                or "/" in raw_title
                or (len(raw_title) > 2 and raw_title[1] == ":" and raw_title[0].isalpha())
                or any(raw_title.lower().endswith(ext) for ext in [".pmd", ".pdf", ".indd", ".doc", ".docx", ".qxd", ".tex"])
            )
            metadata["title"] = Path(filename).stem if is_path_or_source else raw_title
            metadata["author"] = pdf_meta.get("author")
            
            # Format creation date if present
            raw_date = pdf_meta.get("creationDate")
            if raw_date and raw_date.startswith("D:"):
                try:
                    # PDF date format: D:YYYYMMDDHHmmSS
                    cleaned = raw_date[2:16]
                    metadata["creation_date"] = datetime.strptime(cleaned, "%Y%m%d%H%M%S")
                except Exception:
                    metadata["creation_date"] = None

            # Determine format version
            metadata["pdf_version"] = f"1.{doc.pdf_version()}" if hasattr(doc, "pdf_version") else "1.7"
            doc.close()
        except Exception as e:
            metadata["error"] = str(e)

        return metadata
