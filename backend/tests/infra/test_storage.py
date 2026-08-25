from io import BytesIO
from pathlib import Path

from botocore.exceptions import ClientError

from app.infra.config import S3Settings
from app.infra.storage import ObjectStorage, create_object_storage, create_s3_client


def test_s3_settings_load_from_environment(monkeypatch) -> None:
    monkeypatch.setenv("S3_ENDPOINT_URL", "http://localhost:9000")
    monkeypatch.setenv("S3_ACCESS_KEY_ID", "example-access-key")
    monkeypatch.setenv("S3_SECRET_ACCESS_KEY", "example-secret-key")
    monkeypatch.setenv("S3_BUCKET_NAME", "clips")
    monkeypatch.setenv("S3_REGION", "us-east-1")
    monkeypatch.setenv("S3_USE_SSL", "false")

    settings = S3Settings()

    assert settings.s3_endpoint_url == "http://localhost:9000"
    assert settings.s3_access_key_id == "example-access-key"
    assert settings.s3_secret_access_key == "example-secret-key"
    assert settings.s3_bucket_name == "clips"
    assert settings.s3_region == "us-east-1"
    assert settings.s3_use_ssl is False


def test_create_s3_client_uses_settings(monkeypatch) -> None:
    calls = {}

    def fake_boto3_client(service_name, **kwargs):
        calls["service_name"] = service_name
        calls["kwargs"] = kwargs
        return object()

    monkeypatch.setattr("app.infra.storage.boto3.client", fake_boto3_client)

    settings = S3Settings(
        s3_endpoint_url="http://localhost:9000",
        s3_access_key_id="example-access-key",
        s3_secret_access_key="example-secret-key",
        s3_bucket_name="clips",
        s3_region="us-east-1",
        s3_use_ssl=False,
    )

    create_s3_client(settings)

    assert calls["service_name"] == "s3"
    assert calls["kwargs"] == {
        "endpoint_url": "http://localhost:9000",
        "aws_access_key_id": "example-access-key",
        "aws_secret_access_key": "example-secret-key",
        "region_name": "us-east-1",
        "use_ssl": False,
    }


def test_create_object_storage_returns_abstraction(monkeypatch) -> None:
    client = object()
    monkeypatch.setattr("app.infra.storage.create_s3_client", lambda settings: client)

    settings = S3Settings(
        s3_access_key_id="example-access-key",
        s3_secret_access_key="example-secret-key",
        s3_bucket_name="clips",
    )

    storage = create_object_storage(settings)

    assert storage.client is client
    assert storage.bucket_name == "clips"


def test_object_storage_methods_delegate_to_client() -> None:
    client = FakeS3Client()
    storage = ObjectStorage(client=client, bucket_name="clips")

    storage.upload_file(Path("video.mp4"), "raw/video.mp4")
    storage.upload_fileobj(BytesIO(b"video"), "raw/stream.mp4", content_type="video/mp4")
    storage.put_object("raw/data.txt", b"hello", content_type="text/plain")
    storage.download_file("raw/video.mp4", Path("downloaded.mp4"))
    assert storage.read_object("raw/data.txt") == b"hello"
    storage.delete_object("raw/data.txt")
    assert storage.exists("raw/video.mp4") is True

    assert client.calls == [
        ("upload_file", "video.mp4", "clips", "raw/video.mp4"),
        ("upload_fileobj", "clips", "raw/stream.mp4", "video/mp4"),
        ("put_object", "clips", "raw/data.txt", b"hello", "text/plain"),
        ("download_file", "clips", "raw/video.mp4", "downloaded.mp4"),
        ("get_object", "clips", "raw/data.txt"),
        ("delete_object", "clips", "raw/data.txt"),
        ("head_object", "clips", "raw/video.mp4"),
    ]


def test_object_storage_exists_returns_false_for_missing_object() -> None:
    storage = ObjectStorage(client=MissingObjectS3Client(), bucket_name="clips")

    assert storage.exists("missing.mp4") is False


class FakeS3Client:
    def __init__(self) -> None:
        self.calls = []

    def upload_file(self, file_path, bucket, key) -> None:
        self.calls.append(("upload_file", file_path, bucket, key))

    def upload_fileobj(self, fileobj, bucket, key, ExtraArgs=None) -> None:
        self.calls.append(("upload_fileobj", bucket, key, ExtraArgs["ContentType"]))

    def put_object(self, Bucket, Key, Body, ContentType=None) -> None:
        self.calls.append(("put_object", Bucket, Key, Body, ContentType))

    def download_file(self, bucket, key, destination_path) -> None:
        self.calls.append(("download_file", bucket, key, destination_path))

    def get_object(self, Bucket, Key):
        self.calls.append(("get_object", Bucket, Key))
        return {"Body": BytesIO(b"hello")}

    def delete_object(self, Bucket, Key) -> None:
        self.calls.append(("delete_object", Bucket, Key))

    def head_object(self, Bucket, Key) -> None:
        self.calls.append(("head_object", Bucket, Key))


class MissingObjectS3Client:
    def head_object(self, Bucket, Key) -> None:
        raise ClientError({"Error": {"Code": "404"}}, "HeadObject")
