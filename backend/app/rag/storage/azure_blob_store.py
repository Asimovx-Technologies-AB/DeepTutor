"""
Azure Blob Storage adapter for DeepTutor document storage.
Supports Azure Managed Identity and Connection Strings.
"""
import logging
import os
from pathlib import Path
from typing import Optional

from app.core.config import get_settings

logger = logging.getLogger(__name__)


class AzureBlobStore:
    """Client for Azure Blob Storage for uploaded textbooks and document assets."""

    def __init__(self):
        self.settings = get_settings()
        self.container_name = self.settings.documents_container
        self._client = None
        self._container_client = None

    def _get_client(self):
        if self._client is not None:
            return self._client

        conn_str = self.settings.AZURE_STORAGE_CONNECTION_STRING
        account_name = self.settings.AZURE_STORAGE_ACCOUNT_NAME

        try:
            from azure.storage.blob import BlobServiceClient
        except ImportError:
            logger.warning("[AzureBlobStore] azure-storage-blob not installed. Operating in offline/local mode.")
            return None

        if conn_str:
            self._client = BlobServiceClient.from_connection_string(conn_str)
        elif account_name:
            # Managed identity on Azure Container Apps
            try:
                from azure.identity import DefaultAzureCredential
                account_url = f"https://{account_name}.blob.core.windows.net"
                self._client = BlobServiceClient(account_url=account_url, credential=DefaultAzureCredential())
            except Exception as e:
                logger.warning(f"[AzureBlobStore] DefaultAzureCredential failed: {e}")
                return None
        else:
            logger.info("[AzureBlobStore] No Azure Blob credentials configured. Operating in local mode.")
            return None

        # Ensure container exists
        if self._client:
            try:
                self._container_client = self._client.get_container_client(self.container_name)
                if not self._container_client.exists():
                    self._container_client.create_container()
            except Exception as e:
                logger.warning(f"[AzureBlobStore] Error initializing container: {e}")

        return self._client

    def upload_file(self, local_path: str, blob_name: str) -> str:
        """Upload a file from local filesystem to Azure Blob Storage."""
        client = self._get_client()
        if not client or not self._container_client:
            logger.info(f"[AzureBlobStore] Local storage fallback: {local_path}")
            return str(local_path)

        blob_client = self._container_client.get_blob_client(blob_name)
        with open(local_path, "rb") as data:
            blob_client.upload_blob(data, overwrite=True)
        return blob_client.url

    def upload_bytes(self, data: bytes, blob_name: str, content_type: str = "application/octet-stream") -> str:
        """Upload raw bytes to Azure Blob Storage."""
        client = self._get_client()
        if not client or not self._container_client:
            return blob_name

        from azure.storage.blob import ContentSettings
        blob_client = self._container_client.get_blob_client(blob_name)
        blob_client.upload_blob(
            data,
            overwrite=True,
            content_settings=ContentSettings(content_type=content_type)
        )
        return blob_client.url

    def download_file(self, blob_name: str, local_path: str) -> bool:
        """Download a blob to a local path."""
        client = self._get_client()
        if not client or not self._container_client:
            return False

        try:
            blob_client = self._container_client.get_blob_client(blob_name)
            Path(local_path).parent.mkdir(parents=True, exist_ok=True)
            with open(local_path, "wb") as download_file:
                download_file.write(blob_client.download_blob().readall())
            return True
        except Exception as e:
            logger.error(f"[AzureBlobStore] Download error for {blob_name}: {e}")
            return False

    def ensure_local_copy(self, blob_name: str, local_path: str) -> str:
        """Ensures file exists on local ephemeral disk, restoring from Azure Blob if missing."""
        path_obj = Path(local_path)
        if path_obj.exists() and path_obj.stat().st_size > 0:
            return local_path

        if self.download_file(blob_name, local_path):
            logger.info(f"[AzureBlobStore] Restored missing blob {blob_name} to {local_path}")
            return local_path
        return local_path

    def delete_file(self, blob_name: str) -> bool:
        """Delete a blob."""
        client = self._get_client()
        if not client or not self._container_client:
            return False

        try:
            blob_client = self._container_client.get_blob_client(blob_name)
            blob_client.delete_blob()
            return True
        except Exception as e:
            logger.error(f"[AzureBlobStore] Delete error for {blob_name}: {e}")
            return False

    def get_url(self, blob_name: str) -> str:
        """Get the URL for a blob."""
        if not self._container_client:
            return blob_name
        blob_client = self._container_client.get_blob_client(blob_name)
        return blob_client.url


azure_blob_store = AzureBlobStore()
