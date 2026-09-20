"""Upload service unit tests: sanitization, storage keys, limits, media validation."""
import io
import uuid
from pathlib import Path

import pytest

from app.core.config import Settings
from app.core.errors import AppError
from app.services.ingest import upload_service


def test_sanitize_filename_basic() -> None:
    assert upload_service.sanitize_filename("My Video (Final).MP4") == "my-video-final-.mp4"


def test_sanitize_filename_strips_paths_and_weird() -> None:
    assert upload_service.sanitize_filename("../../etc/passwd") == "passwd"
    assert upload_service.sanitize_filename("видео №5.mp4") == "5.mp4"
    assert upload_service.sanitize_filename("a@b#c$d.mp4") == "a-b-c-d.mp4"


def test_sanitize_filename_empty_and_long() -> None:
    assert upload_service.sanitize_filename("") == "video"
    assert upload_service.sanitize_filename(".") == "video"
    long_name = "x" * 200 + ".mp4"
    assert len(upload_service.sanitize_filename(long_name)) == 80


def test_sanitize_filename_no_traversal() -> None:
    for name in ("..mp4", "....mp4", "-.mp4"):
        assert ".." not in upload_service.sanitize_filename(name)


def test_build_storage_key() -> None:
    vid = uuid.uuid4()
    key = upload_service.build_storage_key(vid, "clip.mp4")
    assert key == f"videos/{vid}/clip.mp4"


def test_validate_media_rejects_ext() -> None:
    with pytest.raises(AppError) as e:
        upload_service.validate_media("movie.avi", "video/mp4")
    assert e.value.status_code == 415
    assert e.value.code == "unsupported_media"


def test_validate_media_rejects_mime() -> None:
    with pytest.raises(AppError) as e:
        upload_service.validate_media("movie.mp4", "image/png")
    assert e.value.status_code == 415


def test_validate_media_accepts_all_allowed() -> None:
    for ext, mime in [
        (".mp4", "video/mp4"), (".mov", "video/quicktime"),
        (".webm", "video/webm"), (".mkv", "video/x-matroska"),
    ]:
        upload_service.validate_media(f"v{ext}", mime)


def test_check_content_length_413() -> None:
    settings = Settings(_env_file=None, upload_max_mb=1)
    with pytest.raises(AppError) as e:
        upload_service.check_content_length(4 * 1024 * 1024, settings)
    assert e.value.status_code == 413
    upload_service.check_content_length(1024, settings)  # small is fine
    upload_service.check_content_length(None, settings)  # absent is fine


def test_stream_to_file_rejects_empty() -> None:
    settings = Settings(_env_file=None)
    with pytest.raises(AppError) as e:
        upload_service.stream_to_file(io.BytesIO(b""), Path("/tmp/x"), settings)
    assert e.value.code == "empty_file"


def test_stream_to_file_enforces_limit() -> None:
    settings = Settings(_env_file=None, upload_max_mb=0)  # any byte exceeds 0 MB
    with pytest.raises(AppError) as e:
        upload_service.stream_to_file(io.BytesIO(b"abc"), Path("/tmp/y"), settings)
    assert e.value.status_code == 413


def test_stream_to_file_writes_chunks(tmp_path) -> None:
    settings = Settings(_env_file=None, upload_max_mb=10)
    target = tmp_path / "out.bin"
    n = upload_service.stream_to_file(io.BytesIO(b"hello world"), target, settings)
    assert n == 11
    assert target.read_bytes() == b"hello world"
