"""Metrics sync — official platform APIs only (master spec §22).

TikTok: Display API v2 `POST /v2/video/query/?fields=...` with
filters.video_ids (official docs, see KNOWLEDGE §2, checked 2026-09-20).
Scope: video.list. Returns view/like/comment/share counts for our own posts.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Protocol

import httpx

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.core.logging import get_logger
from app.core.security import decrypt_str
from app.models.job import Job, JobRefType, JobStatus, JobType
from app.models.metric import Metric
from app.models.platform_account import PlatformAccount
from app.models.publication import Publication, PublicationStatus

logger = get_logger(__name__)

DEFAULT_BASE_URL = "https://open.tiktokapis.com"
TIKTOK_QUERY_FIELDS = "id,view_count,like_count,comment_count,share_count"


class MetricsError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class MetricsAdapter(Protocol):
    platform: str

    def fetch(self, external_post_id: str, credentials: dict) -> dict:
        """Return {"views","likes","comments","shares","raw"} (values may be None)."""
        ...  # pragma: no cover


class TikTokMetricsAdapter:
    platform = "tiktok"

    def __init__(self, base_url: str = DEFAULT_BASE_URL, transport=None) -> None:
        self.base_url = base_url.rstrip("/")
        self.transport = transport

    def fetch(self, external_post_id: str, credentials: dict) -> dict:
        token = (credentials or {}).get("access_token")
        if not token:
            raise MetricsError("missing_credentials", "PlatformAccount has no access_token")
        try:
            with httpx.Client(timeout=30, transport=self.transport) as client:
                response = client.post(
                    f"{self.base_url}/v2/video/query/?fields={TIKTOK_QUERY_FIELDS}",
                    json={"filters": {"video_ids": [external_post_id]}},
                    headers={"Authorization": f"Bearer {token}"},
                )
        except httpx.HTTPError as exc:
            raise MetricsError("network_error", f"TikTok metrics request failed: {exc}") from exc
        try:
            body = response.json()
        except ValueError:
            raise MetricsError("invalid_response", f"non-JSON response HTTP {response.status_code}") from None
        error = body.get("error") or {}
        if response.status_code != 200 or error.get("code") not in (None, "ok"):
            raise MetricsError(error.get("code") or f"http_{response.status_code}",
                               error.get("message") or "metrics query failed")
        videos = (body.get("data") or {}).get("videos") or []
        if not videos:
            raise MetricsError("video_not_found", f"TikTok returned no video for id {external_post_id}")
        video = videos[0]
        return {
            "views": video.get("view_count"),
            "likes": video.get("like_count"),
            "comments": video.get("comment_count"),
            "shares": video.get("share_count"),
            "raw": body,
        }


_ADAPTERS: dict[str, type] = {}


def register_adapter(cls):
    _ADAPTERS[cls.platform] = cls
    return cls


register_adapter(TikTokMetricsAdapter)


def get_metrics_adapter(platform: str, **kwargs) -> MetricsAdapter:
    cls = _ADAPTERS.get(platform)
    if cls is None:
        raise MetricsError("unsupported_platform", f"No metrics adapter for '{platform}'")
    return cls(**kwargs)


def queue_metrics_sync(db: Session, publication_id: uuid.UUID) -> Job:
    publication = db.get(Publication, publication_id)
    if publication is None:
        raise AppError(404, "publication_not_found", f"Publication {publication_id} not found")
    if publication.status != PublicationStatus.PUBLISHED:
        raise AppError(409, "publication_not_published", "Only published posts have metrics")
    if not publication.external_post_id:
        raise AppError(409, "publication_not_published", "Publication has no external post id")

    job = Job(
        job_type=JobType.METRICS_SYNC,
        ref_type=JobRefType.PUBLICATION,
        ref_id=publication_id,
        status=JobStatus.QUEUED,
        payload={"publication_id": str(publication_id)},
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


def execute_metrics_sync(db: Session, job_id: uuid.UUID) -> Job:
    """Fetch + store one metric snapshot. Controlled failures -> job failed."""
    job = db.get(Job, job_id)
    if job is None:
        raise ValueError(f"Job {job_id} not found")
    job.status = JobStatus.RUNNING
    db.commit()
    try:
        publication = db.get(Publication, job.ref_id)
        if publication is None or not publication.external_post_id:
            raise MetricsError("publication_not_published", "no external post id")

        account = db.get(PlatformAccount, publication.platform_account_id)
        credentials = json.loads(decrypt_str(account.credentials_encrypted))
        adapter = get_metrics_adapter(publication.platform)
        data = adapter.fetch(publication.external_post_id, credentials)

        metric = Metric(
            publication_id=publication.id,
            views=data.get("views"),
            likes=data.get("likes"),
            comments=data.get("comments"),
            shares=data.get("shares"),
            raw=data.get("raw", {}),
        )
        db.add(metric)
        job.result = {
            "metric_id": str(metric.id),
            "views": data.get("views"),
            "likes": data.get("likes"),
            "comments": data.get("comments"),
            "shares": data.get("shares"),
            "captured_at": datetime.now(timezone.utc).isoformat(),
        }
        job.status = JobStatus.SUCCEEDED
        db.commit()
    except MetricsError as exc:
        job.status = JobStatus.FAILED
        job.error_message = f"{exc.code}: {exc.message}"[:2000]
        db.commit()
    except Exception as exc:  # noqa: BLE001
        logger.exception("metrics sync crashed")
        job.status = JobStatus.FAILED
        job.error_message = f"internal_error: {exc}"[:2000]
        db.commit()
    db.refresh(job)
    return job


def sync_all_published(db: Session, limit: int = 50) -> dict:
    """Beat entry: create metrics_sync jobs for all published publications."""
    published = db.scalars(
        select(Publication)
        .where(Publication.status == PublicationStatus.PUBLISHED,
               Publication.external_post_id.is_not(None))
        .order_by(Publication.published_at.desc())
        .limit(limit)
    )
    queued = 0
    for publication in published:
        queue_metrics_sync(db, publication.id)
        queued += 1
    return {"queued": queued}


def list_metrics(db: Session, publication_id: uuid.UUID) -> list[Metric]:
    return list(db.scalars(
        select(Metric).where(Metric.publication_id == publication_id)
        .order_by(Metric.captured_at)
    ))
