"""Worker CLI entry point: celery -A app.workers.celery_app worker"""
from app.infra.queue import celery_app

__all__ = ["celery_app"]
