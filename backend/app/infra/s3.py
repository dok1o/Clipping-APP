"""S3-compatible storage — the ONLY module allowed to import boto3 (master spec §6).

All other code gets object bytes / presigned URLs / local files through this class.
Works with MinIO locally and any S3 via env (endpoint, region, keys, SSL).
"""
from pathlib import Path
from typing import BinaryIO

import boto3
from botocore.config import Config

from app.core.config import Settings
from app.core.logging import get_logger

logger = get_logger(__name__)


class S3Storage:
    def __init__(
        self,
        endpoint_url: str,
        region: str,
        bucket: str,
        access_key: str,
        secret_key: str,
        use_ssl: bool = False,
    ) -> None:
        self.endpoint_url = endpoint_url
        self.region = region
        self.bucket = bucket
        self.access_key = access_key
        self.secret_key = secret_key
        self.use_ssl = use_ssl
        self._client = None

    @classmethod
    def from_settings(cls, settings: Settings) -> "S3Storage":
        return cls(
            endpoint_url=settings.s3_endpoint,
            region=settings.s3_region,
            bucket=settings.s3_bucket,
            access_key=settings.s3_access_key,
            secret_key=settings.s3_secret_key,
            use_ssl=settings.s3_use_ssl,
        )

    @property
    def client(self):
        if self._client is None:
            self._client = boto3.client(
                "s3",
                endpoint_url=self.endpoint_url,
                region_name=self.region,
                aws_access_key_id=self.access_key,
                aws_secret_access_key=self.secret_key,
                config=Config(
                    signature_version="s3v4",
                    s3={"addressing_style": "path"},  # required by MinIO
                    retries={"max_attempts": 2},
                ),
            )
        return self._client

    def ensure_bucket(self) -> None:
        try:
            self.client.head_bucket(Bucket=self.bucket)
        except Exception:
            self.client.create_bucket(Bucket=self.bucket)
            logger.info("created s3 bucket %s", self.bucket)

    def head_bucket(self) -> None:
        self.client.head_bucket(Bucket=self.bucket)

    def upload_file(self, local_path: str | Path, key: str, content_type: str | None = None) -> None:
        extra = {"ContentType": content_type} if content_type else None
        self.client.upload_file(str(local_path), self.bucket, key, ExtraArgs=extra)

    def upload_fileobj(self, fileobj: BinaryIO, key: str, content_type: str | None = None) -> None:
        extra = {"ContentType": content_type} if content_type else None
        self.client.upload_fileobj(fileobj, self.bucket, key, ExtraArgs=extra)

    def download_to_file(self, key: str, local_path: str | Path) -> None:
        self.client.download_file(self.bucket, key, str(local_path))

    def get_object_bytes(self, key: str) -> bytes:
        resp = self.client.get_object(Bucket=self.bucket, Key=key)
        return resp["Body"].read()

    def exists(self, key: str) -> bool:
        try:
            self.client.head_object(Bucket=self.bucket, Key=key)
            return True
        except Exception:
            return False

    def delete_object(self, key: str) -> None:
        self.client.delete_object(Bucket=self.bucket, Key=key)

    def presigned_get(self, key: str, expires_sec: int = 900) -> str:
        return self.client.generate_presigned_url(
            "get_object", Params={"Bucket": self.bucket, "Key": key}, ExpiresIn=expires_sec
        )
