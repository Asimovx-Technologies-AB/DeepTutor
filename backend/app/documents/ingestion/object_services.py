"""
Object Services — File persistence, deduplication, and cloud backup.

Handles document registration in the database, SHA-256 dedup checking,
and Azure Blob Storage backup.  Calls into the existing dedup and
blob-store modules rather than duplicating their logic.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from app.documents.ingestion.file_handler import FileHandler
from app.documents.models import PipelineDocument

logger = logging.getLogger(__name__)


class ObjectServices:
    """Registers documents, checks duplicates, and triggers cloud backup."""

    def __init__(self) -> None:
        self.file_handler = FileHandler()

    # ── Document registration ─────────────────────────────────────────────

    async def register_document(
        self,
        doc_id: str,
        file_path: str,
        file_name: str,
        session_id: str,
        user_id: Optional[str] = None,
        subject: str = "General",
        doc_hash: Optional[str] = None,
    ) -> PipelineDocument:
        """Validates the file, registers it in the DB, and triggers backup.

        Returns a fully populated PipelineDocument in RECEIVED status.
        """
        # 1. Validate
        ok, err = self.file_handler.validate(file_path)
        if not ok:
            raise ValueError(err)

        # 2. Create pipeline document (detects format + computes hash)
        document = self.file_handler.create_pipeline_document(
            doc_id=doc_id,
            file_path=file_path,
            file_name=file_name,
            session_id=session_id,
            user_id=user_id,
            subject=subject,
            doc_hash=doc_hash,
        )

        # 3. Persist to session DB via existing study_storage functions
        try:
            from app.services.study_storage import (
                init_session_db,
                save_session_document,
            )

            init_session_db(session_id)
            save_session_document(
                session_id=session_id,
                doc_id=doc_id,
                filename=file_name,
                file_path=file_path,
                status="indexing",
                user_id=user_id,
                doc_hash=document.doc_hash,
            )
        except Exception as exc:
            logger.warning("[ObjectServices] DB registration notice: %s", exc)

        # 4. Trigger cloud backup (non-blocking, best-effort)
        await self._ensure_cloud_backup(file_path, session_id, file_name)

        return document

    # ── Deduplication ─────────────────────────────────────────────────────

    @staticmethod
    def check_duplicate(doc_hash: str, user_id: str) -> Optional[str]:
        """Checks if this content hash was already processed for the user.

        Returns the existing doc_id if duplicate, else None.
        """
        try:
            from app.rag.document_dedup import is_already_processed

            if is_already_processed(doc_hash, user_id):
                return doc_hash  # signals duplicate
        except Exception as exc:
            logger.debug("[ObjectServices] Dedup check notice: %s", exc)
        return None

    # ── Cloud backup ──────────────────────────────────────────────────────

    @staticmethod
    async def _ensure_cloud_backup(
        file_path: str, session_id: str, file_name: str
    ) -> None:
        """Uploads the file to Azure Blob Storage if available."""
        try:
            from app.rag.storage.azure_blob_store import azure_blob_store

            blob_name = f"documents/{session_id}/{file_name}"
            if Path(file_path).exists():
                azure_blob_store.upload_file(file_path, blob_name)
            else:
                azure_blob_store.ensure_local_copy(blob_name, file_path)
        except Exception as exc:
            logger.debug("[ObjectServices] Azure Blob backup notice: %s", exc)
