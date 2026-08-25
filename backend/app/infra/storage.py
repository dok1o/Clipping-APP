from __future__ import annotations

from pathlib import Path
from typing import Any

import boto3
from botocore.exceptions import ClientError

from app.infra.config import S3Settings, get_s3_settings


class ObjectStorage:
    def __init__(self, client: Any, bucket_name: str) -> None:
        self.client = client
        self.bucket_name = bucket_name

    def upload_file(self, file_path: str | Path, object_key: str) -> None:
        self.client.upload_file(str(file_path), self.bucket_name, object_key)

    def put_object(self, object_key: str, data: bytes, content_type: str | None = None) -> None:
        kwargs: dict[str, Any] = {
            "Bucket": self.bucket_name,
            "Key": object_key,
            "Body": data,
        }
        if content_type is not None:
            kwargs["ContentType"] = content_type
        self.client.put_object(**kwargs)

    def download_file(self, object_key: str, destination_path: str | Path) -> None:
        self.client.download_file(self.bucket_name, object_key, str(destination_path))

    def read_object(self, object_key: str) -> bytes:
        response = self.client.get_object(Bucket=self.bucket_name, Key=object_key)
        return response["Body"].read()

    def delete_object(self, object_key: str) -> None:
        self.client.delete_object(Bucket=self.bucket_name, Key=object_key)

    def exists(self, object_key: str) -> bool:
        try:
            self.client.head_object(Bucket=self.bucket_name, Key=object_key)
        except ClientError as exc:
            error_code = exc.response.get("Error", {}).get("Code")
            if error_code in {"404", "NoSuchKey", "NotFound"}:
                return False
            raise
        return True


def create_s3_client(settings: S3Settings | None = None) -> Any:
    s3_settings = settings or get_s3_settings()
    return boto3.client(
        "s3",
        endpoint_url=s3_settings.s3_endpoint_url,
        aws_access_key_id=s3_settings.s3_access_key_id,
        aws_secret_access_key=s3_settings.s3_secret_access_key,
        region_name=s3_settings.s3_region,
        use_ssl=s3_settings.s3_use_ssl,
    )


def create_object_storage(settings: S3Settings | None = None) -> ObjectStorage:
    s3_settings = settings or get_s3_settings()
    return ObjectStorage(
        client=create_s3_client(s3_settings),
        bucket_name=s3_settings.s3_bucket_name,
    )
