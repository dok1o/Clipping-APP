#!/usr/bin/env python3
"""YouTube integration verification (Stage 8; real run needs Google OAuth keys).

Modes:
  --dry-run (default): no network — validates registry wiring, request
      construction against the official resumable protocol (mock transport),
      metadata limits, metrics adapter. Safe anywhere.
  --real: calls the REAL YouTube Data API v3 (token refresh + videos.list
      statistics for YOUTUBE_VERIFY_VIDEO_ID, upload of a tiny mp4 is NOT
      performed to not burn quota). Requires YOUTUBE_* env. Never run in CI.

Honest PASS / FAIL / SKIP.
"""
import argparse
import io
import json
import os
import sys
import tempfile
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND_DIR))

REQUIRED_ENV = ["YOUTUBE_CLIENT_ID", "YOUTUBE_CLIENT_SECRET", "YOUTUBE_REFRESH_TOKEN"]
SESSION_URL = "https://www.googleapis.com/upload/youtube/v3/videos?uploadType=resumable&upload_id=verify"


def dry_run() -> int:
    import httpx

    from app.services.publish.base import PublishRequest
    from app.services.publish.youtube import PRIVACY_MAP, YouTubePublisher

    ok = True

    # 1) registry wiring
    from app.services.publish.base import get_publisher

    publisher = get_publisher("youtube")
    print("PASS  registry resolves youtube ->", type(publisher).__name__)

    # 2) official resumable protocol against a mock
    state = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST" and "/upload/youtube/v3/videos" in str(request.url):
            state["init"] = json.loads(request.content)
            assert request.url.params.get("uploadType") == "resumable"
            return httpx.Response(200, headers={"Location": SESSION_URL})
        if request.method == "PUT":
            state["bytes"] = request.content
            return httpx.Response(200, json={"id": "vid-verify", "status": {"uploadStatus": "uploaded"}})
        raise AssertionError(f"unexpected {request.method} {request.url}")

    with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tmp:
        tmp.write(b"\x00\x00\x00\x18ftypmp42verify")
        video_path = tmp.name
    try:
        result = YouTubePublisher(transport=httpx.MockTransport(handler)).publish(
            PublishRequest(video_path=video_path, title="verify", privacy="unlisted",
                           tags=["shorts"]),
            credentials={"access_token": "dry"},
        )
    finally:
        Path(video_path).unlink(missing_ok=True)

    if result.external_post_id == "vid-verify" and state.get("init", {}).get("status", {}).get("privacyStatus") == "unlisted":
        print("PASS  resumable two-step upload (init metadata + PUT bytes), privacy=unlisted")
    else:
        print("FAIL  resumable upload:", result)
        ok = False

    # 3) metadata limits
    meta = YouTubePublisher()._build_metadata(
        PublishRequest(video_path=video_path, title="x" * 300, privacy="public", tags=["t" * 60] * 20)
    )
    if len(meta["snippet"]["title"]) == 100 and sum(len(t) + 1 for t in meta["snippet"]["tags"]) <= 500:
        print("PASS  title<=100 and tags<=500 chars enforced")
    else:
        print("FAIL  metadata limits")
        ok = False

    # 4) metrics adapter wiring
    from app.services.analytics.metrics_service import get_metrics_adapter

    adapter = get_metrics_adapter("youtube")
    print("PASS  metrics registry resolves youtube ->", type(adapter).__name__)

    # 5) privacy map is native 1:1
    if PRIVACY_MAP == {"public": "public", "unlisted": "unlisted", "private": "private"}:
        print("PASS  privacy map 1:1 (native YouTube statuses)")
    else:
        print("FAIL  privacy map:", PRIVACY_MAP)
        ok = False

    return 0 if ok else 1


def real_run() -> int:
    missing = [key for key in REQUIRED_ENV if not os.environ.get(key)]
    if missing:
        print(f"SKIP  --real needs env: {', '.join(missing)}")
        return 2

    from app.services.analytics.metrics_service import YouTubeMetricsAdapter
    from app.services.publish.youtube import resolve_access_token

    try:
        token = resolve_access_token({
            "refresh_token": os.environ["YOUTUBE_REFRESH_TOKEN"],
            "client_id": os.environ["YOUTUBE_CLIENT_ID"],
            "client_secret": os.environ["YOUTUBE_CLIENT_SECRET"],
        })
        print("PASS  OAuth2 refresh_token -> access token received")
    except Exception as exc:  # noqa: BLE001
        print("FAIL  token refresh:", exc)
        return 1

    video_id = os.environ.get("YOUTUBE_VERIFY_VIDEO_ID", "")
    if not video_id:
        print("SKIP  metrics check (set YOUTUBE_VERIFY_VIDEO_ID to one of your video ids)")
        return 0
    try:
        data = YouTubeMetricsAdapter().fetch(video_id, {"access_token": token})
        print(f"PASS  videos.list statistics: views={data['views']} likes={data['likes']}")
        return 0
    except Exception as exc:  # noqa: BLE001
        print("FAIL  metrics:", exc)
        return 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--real", action="store_true", help="call the real API (needs keys)")
    parser.add_argument("--json", dest="as_json", action="store_true", help="machine-readable output")
    args = parser.parse_args()
    if args.as_json:
        print(json.dumps({"mode": "real" if args.real else "dry-run"}))
    return real_run() if args.real else dry_run()


if __name__ == "__main__":
    raise SystemExit(main())
