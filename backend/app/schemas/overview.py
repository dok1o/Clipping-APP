"""Overview (home dashboard) schemas — one aggregate call instead of client N+1."""
from typing import Any

from pydantic import BaseModel


class OverviewStats(BaseModel):
    videos: dict[str, int]            # status -> count
    clips: dict[str, int]             # status -> count
    jobs: dict[str, int]              # status -> count
    publications: dict[str, int]      # status -> count
    scheduled_next_at: str | None = None
    failed_jobs_recent: int           # failed jobs in the last 24h
    latest_metrics: dict[str, int]    # {"publications": n, "views": n, "likes": n, ...}
    ml: dict[str, Any]                # {"dataset_rows": n, "active_model": {...} | None}
