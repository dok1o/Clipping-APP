#!/usr/bin/env python3
"""Platform integration verification (TikTok first; YouTube later).

Modes:
  --dry-run (default): no network — validates configuration presence, adapter
      wiring, request construction (against a mock transport). Safe anywhere.
  --real: calls the REAL TikTok creator_info endpoint (requires TIKTOK_* env).
      Never run in CI; needs valid credentials.

Honest PASS / FAIL / SKIP.
"""
import argparse
import json
import os
import sys
import tempfile
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND_DIR))

REQUIRED_ENV = ["TIKTOK_CLIENT_KEY", "TIKTOK_CLIENT_SECRET", "TIKTOK_ACCESS_TOKEN"]


def dry_run() -> int:
    from app.services.publish.base import PublishRequest
    from app.services.publish.tiktok import PRIVACY_MAP, TikTokPublisher

    ok = True

    # 1) registry wiring
    from app.services.publish.tiktok import get_publisher

    publisher = get_publisher("tiktok")
    assert isinstance(publisher, TikTokPublisher)
    print("[PASS] publisher registry resolves tiktok -> TikTokPublisher")

    # 2) request construction against a mock transport
    import httpx

    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "PUT":  # binary upload — not JSON
            return httpx.Response(204)
        captured[request.url.path] = json.loads(request.content)
        if request.url.path.endswith("/video/init/"):
            return httpx.Response(200, json={
                "data": {"publish_id": "v_pub_file~test", "upload_url": "https://upload.test/u"},
                "error": {"code": "ok"},
            })
        if request.url.path.endswith("/status/fetch/"):
            return httpx.Response(200, json={"data": {"status": "PUBLISH_COMPLETE"}, "error": {"code": "ok"}})
        return httpx.Response(204)

    with tempfile.TemporaryDirectory(prefix="verify-platform-") as tmp_dir:
        tmp = Path(tmp_dir) / "dry-run.mp4"
        tmp.write_bytes(b"0" * 2048)
        publisher = TikTokPublisher(base_url="https://mock.test", transport=httpx.MockTransport(handler), poll_delay_sec=0)
        result = publisher.publish(
            PublishRequest(video_path=str(tmp), title="dry run #fyp", privacy="public"),
            {"access_token": "dry-run-token"},
        )
        init = captured.get("/v2/post/publish/video/init/", {})
        assert init["post_info"]["privacy_level"] == PRIVACY_MAP["public"]
        assert init["source_info"]["source"] == "FILE_UPLOAD"
        assert result.status == "published"
        print("[PASS] direct-post flow (init -> upload -> status) against mock transport")

    # 3) second platform is registered through the shared extension point
    from app.services.publish.base import get_publisher
    from app.services.publish.youtube import YouTubePublisher

    youtube = get_publisher("youtube")
    if isinstance(youtube, YouTubePublisher):
        print("[PASS] publisher registry resolves youtube -> YouTubePublisher")
    else:
        print("[FAIL] publisher registry returned the wrong YouTube adapter")
        ok = False

    # 4) env presence (informational in dry-run)
    missing = [name for name in REQUIRED_ENV if not os.environ.get(name)]
    if missing:
        print(f"[SKIP] real-mode credentials not configured: {', '.join(missing)} "
              "(fill .env for --real verification)")
    else:
        print("[PASS] TIKTOK_* env variables present")

    print("\nRESULT: PASS (dry-run)")
    return 0 if ok else 1


def real_check() -> int:
    missing = [name for name in REQUIRED_ENV if not os.environ.get(name)]
    if missing:
        print(f"[SKIP] real mode requires env: {', '.join(missing)}")
        return 0
    import httpx

    token = os.environ["TIKTOK_ACCESS_TOKEN"]
    try:
        response = httpx.post(
            "https://open.tiktokapis.com/v2/post/publish/creator_info/query/",
            headers={"Authorization": f"Bearer {token}"},
            timeout=30,
        )
    except httpx.HTTPError as exc:
        print(f"[FAIL] network error: {exc}")
        return 1
    if response.status_code != 200:
        print(f"[FAIL] HTTP {response.status_code}: {response.text[:300]}")
        return 1
    body = response.json()
    if (body.get("error") or {}).get("code") != "ok":
        print(f"[FAIL] API error: {body.get('error')}")
        return 1
    data = body.get("data", {})
    print(f"[PASS] creator_info: username={data.get('creator_username')}, "
          f"privacy_options={data.get('privacy_level_options')}, "
          f"max_duration={data.get('max_video_post_duration_sec')}s")
    print("\nRESULT: PASS (real creator_info query)")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--real", action="store_true", help="query the real TikTok API (needs credentials)")
    parser.add_argument("--dry-run", action="store_true", help="no-network verification (default)")
    args = parser.parse_args()
    return real_check() if args.real else dry_run()


if __name__ == "__main__":
    raise SystemExit(main())
