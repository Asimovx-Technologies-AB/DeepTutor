from abc import ABC, abstractmethod
from typing import BinaryIO, Optional


class BaseObjectStorage(ABC):
    """Abstract interface for storing raw documents and extracted visual assets."""

    @abstractmethod
    def store_file(self, file_bytes: bytes, filename: str, subfolder: str = "raw_documents") -> str:
        """Stores a file and returns its storage URI/path."""
        pass

    @abstractmethod
    def retrieve_file(self, file_path: str) -> bytes:
        """Retrieves file bytes from storage."""
        pass

    @abstractmethod
    def file_exists(self, file_path: str) -> bool:
        """Checks if a file exists."""
        pass

    @abstractmethod
    def delete_file(self, file_path: str) -> bool:
        """Deletes a file from storage."""
        pass
