"""
Content Hash-Based Document Deduplication & Session Linking Module.

Provides:
- SHA-256 content hashing
- Fast duplicate detection per user
- Multi-session document linking without duplicate embedding or storage
- Upload orchestration with rollback safety on indexing failure
- UI status signals for document reuse
"""

import hashlib
import logging
from typing import Dict, List, Any, Optional, Callable
from app.core import database as db_core

logger = logging.getLogger(__name__)


def get_file_hash(file_bytes: bytes) -> str:
    """
    Computes a cryptographic SHA-256 hash of the raw file bytes.
    
    Args:
        file_bytes: Raw binary content of the file.
        
    Returns:
        64-character hexadecimal SHA-256 digest string.
        
    Raises:
        ValueError: If file_bytes is empty or None.
    """
    if not file_bytes:
        raise ValueError("Cannot compute hash for empty file payload.")
    
    hasher = hashlib.sha256()
    hasher.update(file_bytes)
    return hasher.hexdigest()


def is_already_processed(doc_hash: str, user_id: str, db=None) -> bool:
    """
    Checks if a document with this hash has already been successfully processed
    and indexed for this user.
    
    Args:
        doc_hash: SHA-256 hash of the document.
        user_id: ID of the user requesting upload.
        db: Optional database module or connection (defaults to app.core.database).
        
    Returns:
        True if document exists and is indexed/completed, False otherwise.
    """
    db_mod = db or db_core
    doc = db_mod.get_document_by_hash(doc_hash, user_id)
    if not doc:
        return False
    return bool(doc.get("indexed") or doc.get("status") == "completed")


def link_document_to_session(doc_hash: str, session_id: str, user_id: str, db=None) -> bool:
    """
    Links an existing processed document to a session via the session_documents join table.
    
    Args:
        doc_hash: Document SHA-256 hash.
        session_id: Target session ID.
        user_id: User ID.
        db: Optional database module or connection.
        
    Returns:
        True if linked successfully.
    """
    db_mod = db or db_core
    return db_mod.link_document_to_session(doc_hash=doc_hash, session_id=session_id, user_id=user_id)


def handle_upload(
    file_bytes: bytes,
    filename: str,
    session_id: str,
    user_id: str,
    file_path: str = "",
    file_type: str = "",
    db=None,
    process_callback: Optional[Callable[[dict], Any]] = None,
) -> Dict[str, Any]:
    """
    Main upload orchestrator with hash-based deduplication and transaction safety.
    
    Steps:
    1. Computes SHA-256 hash
    2. Checks if hash already exists and is indexed for user
    3. If YES -> links to session and returns status 'already_processed'
    4. If NO -> creates document record, runs chunking/indexing callback,
                records completion, links to session, and returns 'processed'.
    """
    db_mod = db or db_core

    # 1. Compute Content Hash
    try:
        doc_hash = get_file_hash(file_bytes)
    except Exception as e:
        logger.error(f"Failed to calculate file hash for {filename}: {e}")
        return {
            "status": "error",
            "doc_hash": None,
            "filename": filename,
            "chunks_created": 0,
            "message": f"Failed to compute file hash: {str(e)}"
        }

    # 2. Check if already processed
    if is_already_processed(doc_hash, user_id, db=db_mod):
        logger.info(f"Duplicate upload detected: '{filename}' ({doc_hash[:8]}...). Linking to session '{session_id}'.")
        link_document_to_session(doc_hash, session_id, user_id, db=db_mod)
        existing_doc = db_mod.get_document_by_hash(doc_hash, user_id)
        return {
            "status": "already_processed",
            "doc_hash": doc_hash,
            "doc_id": existing_doc.get("id") if existing_doc else None,
            "filename": filename,
            "chunks_created": 0,
            "message": "Document already exists, linked to this session instantly"
        }

    # 3. New Document - Register in DB with 'pending' status
    doc = db_mod.create_document(
        user_id=user_id,
        topic_id=session_id,
        file_name=filename,
        file_path=file_path,
        file_type=file_type,
        doc_hash=doc_hash,
        status="processing",
    )
    doc_id = doc["id"]

    # 4. Process (chunk + embed) if callback provided synchronously
    chunks_created = 0
    if process_callback:
        try:
            res = process_callback(doc)
            if isinstance(res, int):
                chunks_created = res
            elif isinstance(res, dict):
                chunks_created = res.get("chunks_created", 0)
                
            db_mod.update_document_stats(
                doc_id=doc_id,
                indexed=True,
                entity_count=doc.get("entity_count", 0),
                chunk_count=chunks_created,
                status="completed"
            )
        except Exception as exc:
            logger.error(f"Processing failed for document {doc_id} ({filename}): {exc}", exc_info=True)
            db_mod.update_document_stats(
                doc_id=doc_id,
                indexed=False,
                entity_count=0,
                chunk_count=0,
                status="failed",
                error_message=str(exc)
            )
            return {
                "status": "error",
                "doc_hash": doc_hash,
                "doc_id": doc_id,
                "filename": filename,
                "chunks_created": 0,
                "message": f"Processing failed: {str(exc)}"
            }

    # 5. Link to session
    link_document_to_session(doc_hash, session_id, user_id, db=db_mod)

    return {
        "status": "processed",
        "doc_hash": doc_hash,
        "doc_id": doc_id,
        "filename": filename,
        "chunks_created": chunks_created,
        "message": "Document processed and ready"
    }


def get_session_documents(session_id: str, user_id: str, db=None) -> List[Dict[str, Any]]:
    """
    Returns all documents linked to the specified session.
    """
    db_mod = db or db_core
    return db_mod.get_session_documents(session_id, user_id)


def get_document_status_for_ui(session_id: str, user_id: str, db=None) -> List[Dict[str, Any]]:
    """
    Returns document reuse metrics formatted for the student UI.
    """
    db_mod = db or db_core
    return db_mod.get_document_status_for_ui(session_id, user_id)
