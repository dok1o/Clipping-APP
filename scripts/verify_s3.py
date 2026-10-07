#!/usr/bin/env python3
"""Runtime verification of the configured S3 backend (runtime-audit t11.3, §8.2).

Roundtrip through the project's own S3Storage (boto3 stays inside
app/infra/s3.py): connection/bucket -> upload -> exists -> download ->
presigned URL (checked separately from the roundtrip) -> delete.

Honest result codes: PASS / FAIL / SKIP (with the reason). Never prints
credentials; uses a unique temporary key and cleans it up in finally.
"""
import io
import sys
import uuid
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND_DIR))


def main() -> int:
    from app.core.config import get_settings

    settings = get_settings()
    if not settings.s3_access_key or not settings.s3_secret_key:
        print("[SKIP] S3 credentials not configured (S3_ACCESS_KEY / S3_SECRET_KEY empty).")
        print("       Point them at MinIO/moto in .env to run this real check.")
        return 0
    # only names/paths, never values
    print(f"      endpoint={settings.s3_endpoint} bucket={settings.s3_bucket} ssl={settings.s3_use_ssl}")

    from app.infra.s3 import S3Storage

    storage = S3Storage.from_settings(settings)
    key = f"verify/s3-roundtrip-{uuid.uuid4().hex[:12]}.txt"
    payload = b"ai-clipper-verify-s3-roundtrip"
    ok_all = True
    try:
        try:
            storage.ensure_bucket()
            storage.head_bucket()
            print("[PASS] connection + ensure_bucket")
        except Exception as exc:  # noqa: BLE001
            print(f"[FAIL] connection/bucket: {type(exc).__name__}: {exc}")
            print("\nRESULT: FAIL")
            return 1

        try:
            storage.upload_fileobj(io.BytesIO(payload), key, content_type="text/plain")
            print("[PASS] upload (unique verify key)")
        except Exception as exc:  # noqa: BLE001
            print(f"[FAIL] upload: {type(exc).__name__}: {exc}")
            print("\nRESULT: FAIL")
            return 1

        try:
            if not storage.exists(key):
                raise AssertionError("exists() returned False right after upload")
            print("[PASS] exists")
        except Exception as exc:  # noqa: BLE001
            print(f"[FAIL] exists: {type(exc).__name__}: {exc}")
            ok_all = False

        try:
            got = storage.get_object_bytes(key)
            if got != payload:
                raise AssertionError(f"roundtrip bytes mismatch: {got[:32]!r}")
            print("[PASS] download/read (bytes match)")
        except Exception as exc:  # noqa: BLE001
            print(f"[FAIL] download/read: {type(exc).__name__}: {exc}")
            ok_all = False

        # presigned URL — a SEPARATE check from the storage roundtrip
        try:
            import httpx

            url = storage.presigned_get(key, expires_sec=60)
            response = httpx.get(url, timeout=10)
            if response.status_code != 200 or response.content != payload:
                raise AssertionError(f"presigned fetch: HTTP {response.status_code}, {len(response.content)} bytes")
            print("[PASS] presigned URL issued + fetched (bytes match)")
        except Exception as exc:  # noqa: BLE001
            print(f"[FAIL] presigned URL: {type(exc).__name__}: {exc}")
            ok_all = False
    finally:
        try:
            storage.delete_object(key)
            print("[PASS] cleanup (verify key deleted)")
        except Exception as exc:  # noqa: BLE001
            print(f"[WARN] cleanup failed for {key}: {type(exc).__name__}: {exc}")

    print("\nRESULT:", "PASS" if ok_all else "FAIL")
    return 0 if ok_all else 1


if __name__ == "__main__":
    raise SystemExit(main())
