import os
import hashlib
from pathlib import Path
from app.storage.base import BaseObjectStorage
from app.core.config import settings


class LocalObjectStorage(BaseObjectStorage):
    """
    Filesystem-backed Object Storage.
    Organizes files into namespaces:
    - raw_documents/
    - page_images/
    - asset_crops/
    """

    def __init__(self, root_dir: str | None = None):
        self.root_dir = Path(root_dir or settings.STORAGE_ROOT_DIR).resolve()
        self._ensure_directories()

    def _ensure_directories(self):
        for folder in ["raw_documents", "page_images", "asset_crops"]:
            (self.root_dir / folder).mkdir(parents=True, exist_ok=True)

    def _sanitize_path(self, file_path: str) -> Path:
        """
        Resolves the target path and verifies it strictly resides within self.root_dir.
        Raises PermissionError if directory traversal is detected.
        """
        p = Path(file_path)
        if not p.is_absolute():
            resolved = (self.root_dir / p).resolve()
        else:
            resolved = p.resolve()

        root_resolved = self.root_dir.resolve()
        try:
            resolved.relative_to(root_resolved)
        except ValueError:
            raise PermissionError(f"Access denied: path escapes storage root directory: {file_path}")
        return resolved

    def store_file(self, file_bytes: bytes, filename: str, subfolder: str = "raw_documents") -> str:
        # Sanitize filename and subfolder against directory traversal
        clean_filename = Path(filename).name
        clean_subfolder = Path(subfolder).name or "raw_documents"
        
        sha256 = hashlib.sha256(file_bytes).hexdigest()
        ext = Path(clean_filename).suffix
        safe_name = f"{sha256[:16]}_{Path(clean_filename).stem[:32]}{ext}"
        target_dir = self.root_dir / clean_subfolder
        target_dir.mkdir(parents=True, exist_ok=True)
        target_path = target_dir / safe_name
        
        with open(target_path, "wb") as f:
            f.write(file_bytes)
            
        return str(target_path)

    def retrieve_file(self, file_path: str) -> bytes:
        p = self._sanitize_path(file_path)
        if not p.exists():
            raise FileNotFoundError(f"Storage object not found: {file_path}")
        with open(p, "rb") as f:
            return f.read()

    def file_exists(self, file_path: str) -> bool:
        try:
            p = self._sanitize_path(file_path)
            return p.exists()
        except PermissionError:
            return False

    def delete_file(self, file_path: str) -> bool:
        p = self._sanitize_path(file_path)
        if p.exists():
            p.unlink()
            return True
        return False


default_storage = LocalObjectStorage()
