"""Jobs API + Celery eager foundation tests."""
from uuid import uuid4

from app.models.job import Job, JobType


def test_get_job(client, db) -> None:
    job = Job(job_type=JobType.RENDER, ref_type="clip", ref_id=uuid4())
    db.add(job)
    db.commit()

    response = client.get(f"/api/v1/jobs/{job.id}")
    assert response.status_code == 200
    body = response.json()
    assert body["id"] == str(job.id)
    assert body["type"] == "render"
    assert body["status"] == "queued"
    assert body["attempts"] == 0
    assert body["max_attempts"] == 3
    assert body["created_at"].endswith("Z")


def test_get_job_not_found(client) -> None:
    response = client.get(f"/api/v1/jobs/{uuid4()}")
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "job_not_found"


def test_get_job_invalid_uuid(client) -> None:
    response = client.get("/api/v1/jobs/not-a-uuid")
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "validation_error"


def test_celery_eager_ping() -> None:
    from app.workers.tasks import ping

    result = ping.delay()
    assert result.result == "pong"


def test_celery_app_configured_eager_in_tests() -> None:
    from app.infra.queue import celery_app

    assert celery_app.conf.task_always_eager is True
