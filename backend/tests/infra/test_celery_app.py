from app.infra.celery_app import (
    HEALTH_CHECK_TASK_NAME,
    create_celery_app,
)


def test_celery_app_reads_broker_and_backend_from_environment(monkeypatch) -> None:
    monkeypatch.setenv("CELERY_BROKER_URL", "redis://localhost:6379/10")
    monkeypatch.setenv("CELERY_RESULT_BACKEND", "redis://localhost:6379/11")

    app = create_celery_app("test_env_config")

    assert app.conf.broker_url == "redis://localhost:6379/10"
    assert app.conf.result_backend == "redis://localhost:6379/11"


def test_health_check_task_is_registered() -> None:
    app = create_celery_app("test_task_registration")

    assert HEALTH_CHECK_TASK_NAME in app.tasks


def test_health_check_task_runs_in_eager_mode_without_redis() -> None:
    app = create_celery_app("test_eager_mode")
    app.conf.update(task_always_eager=True, task_eager_propagates=True)

    result = app.tasks[HEALTH_CHECK_TASK_NAME].delay()

    assert result.get(timeout=1) == {"status": "ok"}
