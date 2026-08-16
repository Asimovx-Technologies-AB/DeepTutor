"""
AWS S3 Cloud Storage Client for DeepTutor Documents.
Handles streaming uploads to S3, downloading, and generating secure presigned URLs.
"""
import os
from pathlib import Path
from typing import Optional

try:
    import boto3
    from botocore.exceptions import ClientError
    BOTO3_AVAILABLE = True
except ImportError:
    boto3 = None
    ClientError = Exception
    BOTO3_AVAILABLE = False

from app.core.config import get_settings

settings = get_settings()


class S3StorageManager:
    def __init__(self):
        self.bucket_name = settings.AWS_S3_BUCKET_NAME
        self.region = settings.AWS_REGION
        self.enabled = bool(
            BOTO3_AVAILABLE
            and settings.ENABLE_S3_STORAGE
            and settings.AWS_ACCESS_KEY_ID
            and settings.AWS_SECRET_ACCESS_KEY
            and settings.AWS_S3_BUCKET_NAME
        )
        self._client = None

    @property
    def client(self):
        if self._client is None and self.enabled:
            try:
                self._client = boto3.client(
                    "s3",
                    aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
                    aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
                    region_name=self.region,
                )
            except Exception as e:
                print(f"[S3] Failed to initialize S3 client: {e}")
                self._client = None
        return self._client

    def is_configured(self) -> bool:
        return self.enabled and self.client is not None

    def upload_file(self, local_path: str, s3_key: str, content_type: Optional[str] = None) -> Optional[str]:
        """Uploads a local file to S3 and returns the s3_key."""
        if not self.is_configured():
            return None
        try:
            extra_args = {}
            if content_type:
                extra_args["ContentType"] = content_type
            
            self.client.upload_file(
                local_path,
                self.bucket_name,
                s3_key,
                ExtraArgs=extra_args if extra_args else None
            )
            print(f"[S3] Successfully uploaded {local_path} -> s3://{self.bucket_name}/{s3_key}")
            return s3_key
        except ClientError as e:
            print(f"[S3] Upload error for {s3_key}: {e}")
            return None
        except Exception as e:
            print(f"[S3] Unexpected upload error: {e}")
            return None

    def upload_bytes(self, content: bytes, s3_key: str, content_type: Optional[str] = None) -> Optional[str]:
        """Uploads raw bytes to S3 and returns the s3_key."""
        if not self.is_configured():
            return None
        try:
            extra_args = {}
            if content_type:
                extra_args["ContentType"] = content_type

            self.client.put_object(
                Bucket=self.bucket_name,
                Key=s3_key,
                Body=content,
                **extra_args
            )
            print(f"[S3] Successfully uploaded bytes -> s3://{self.bucket_name}/{s3_key}")
            return s3_key
        except Exception as e:
            print(f"[S3] Upload bytes error: {e}")
            return None

    def download_file(self, s3_key: str, local_path: str) -> bool:
        """Downloads an S3 object to local disk."""
        if not self.is_configured():
            return False
        try:
            Path(local_path).parent.mkdir(parents=True, exist_ok=True)
            self.client.download_file(self.bucket_name, s3_key, local_path)
            return True
        except Exception as e:
            print(f"[S3] Download error for {s3_key}: {e}")
            return False

    def delete_file(self, s3_key: str) -> bool:
        """Deletes an object from S3."""
        if not self.is_configured():
            return False
        try:
            self.client.delete_object(Bucket=self.bucket_name, Key=s3_key)
            print(f"[S3] Deleted object s3://{self.bucket_name}/{s3_key}")
            return True
        except Exception as e:
            print(f"[S3] Delete error for {s3_key}: {e}")
            return False

    def get_presigned_download_url(self, s3_key: str, expires_in_seconds: int = 3600) -> Optional[str]:
        """Generates a temporary secure HTTPS presigned download URL."""
        if not self.is_configured():
            return None
        try:
            url = self.client.generate_presigned_url(
                "get_object",
                Params={"Bucket": self.bucket_name, "Key": s3_key},
                ExpiresIn=expires_in_seconds,
            )
            return url
        except Exception as e:
            print(f"[S3] Presigned URL error: {e}")
            return None


s3_store = S3StorageManager()
