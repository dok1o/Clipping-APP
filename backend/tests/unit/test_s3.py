"""S3 storage tests against moto (no real S3/MinIO needed)."""
import io

import pytest

from app.infra.s3 import S3Storage


def test_upload_download_roundtrip(s3_mock) -> None:
    data = b"fake-video-bytes-0123456789"
    s3_mock.upload_fileobj(io.BytesIO(data), "videos/u1/a.mp4", content_type="video/mp4")
    assert s3_mock.exists("videos/u1/a.mp4") is True
    assert s3_mock.get_object_bytes("videos/u1/a.mp4") == data
    assert s3_mock.exists("videos/u1/missing.mp4") is False


def test_upload_download_file(s3_mock, tmp_path) -> None:
    src = tmp_path / "src.bin"
    src.write_bytes(b"payload")
    s3_mock.upload_file(src, "videos/u2/b.mkv")
    dst = tmp_path / "dst.bin"
    s3_mock.download_to_file("videos/u2/b.mkv", dst)
    assert dst.read_bytes() == b"payload"


def test_presigned_url_contains_key(s3_mock) -> None:
    s3_mock.upload_fileobj(io.BytesIO(b"x"), "renders/c/asset.mp4")
    url = s3_mock.presigned_get("renders/c/asset.mp4", expires_sec=900)
    assert "renders/c/asset.mp4" in url
    assert "X-Amz-Signature" in url or "Signature" in url


def test_delete_object(s3_mock) -> None:
    s3_mock.upload_fileobj(io.BytesIO(b"x"), "videos/u3/c.mp4")
    s3_mock.delete_object("videos/u3/c.mp4")
    assert s3_mock.exists("videos/u3/c.mp4") is False


def test_ensure_bucket_idempotent(s3_mock) -> None:
    s3_mock.ensure_bucket()  # second call must not fail
    s3_mock.head_bucket()


def test_from_settings_reads_env() -> None:
    from app.core.config import get_settings

    storage = S3Storage.from_settings(get_settings())
    assert storage.bucket == get_settings().s3_bucket
    assert storage.endpoint_url == get_settings().s3_endpoint
