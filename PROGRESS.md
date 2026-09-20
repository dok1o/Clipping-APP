# PROGRESS.md — журнал Stage/тикетов

> Приоритет: MASTER_SPEC > CONTRACTS > ARCHITECTURE > AGENTS > KNOWLEDGE > **PROGRESS**.
> PROGRESS фиксирует факты и статусы; никогда не противоречит SPEC/контрактам.

## Текущий этап

`Stage 0 — Documentation, skeleton, health, DB, Celery, S3, frontend, audit` (in progress)

---

## Решения/блокеры (top)

- **2026-09-20 (T0.1)**: В репозитории обнаружена частичная реализация предыдущего (Codex) промпта (коммит e3b2d9f «feat: add vertical clip rendering flow») с неканонической структурой (`app/ingestion|video_effects|...`, без `/api/v1`, без Job/PlatformAccount/Publication по §8, без MASTER_SPEC). Решение: пересборка по канону §5 с нуля; старый код сохранён в git-истории, история не переписывалась. ADR-000 в ARCHITECTURE.md. Файл `docs/codex-master-prompt-ai-clipper.md` (документ пользователя) сохранён.
- **2026-09-20 (T0.1)**: Sandbox-ограничения (см. docs/KNOWLEDGE.md §1): нет ffmpeg/ffprobe, нет Docker/PG/Redis/MinIO, нет GPU. Стратегия: основной pytest-сьют на SQLite+moto+Celery-eager; реальные проверки — scripts/verify_*.py с честным SKIP + список проверок на реальной машине в README.
- **Единственная обязательная остановка**: перед T1.4 — вопрос пользователю «YouTube или TikTok первой?».

## Лог тикетов

### T0.1 — Docs + skeleton — DONE (2026-09-20)
- Создано: 6 канонических доков (MASTER_SPEC, CONTRACTS, ARCHITECTURE, AGENTS, KNOWLEDGE, PROGRESS), README.md, .gitignore (§26), .env.example (§25, без секретов), каноническое дерево каталогов §5 (backend/app/{core,db,models,schemas,api/v1,services/*,infra,workers}, backend/alembic/versions, backend/tests/{unit,api,integration}, frontend/src/{pages,components}, scripts/, storage/.gitkeep).
- Удалено (в рамках ADR-000, сохранено в истории): старая неканоническая реализация.
- Тесты: `find . -type d` — дерево совпадает с §5; `grep -c "=" .env.example` — 60+ переменных, секретные поля пустые.
- Статус: DONE.

### T0.2 — Config + FastAPI health + logging/errors — DONE (2026-09-20)
- Файлы: backend/pyproject.toml (+ extras dev/whisper/ml), app/core/{config,logging,errors,security}.py, app/main.py, app/api/{deps,v1/router}.py, tests/{conftest,api/test_health,unit/test_config,unit/test_repo_structure}.py.
- Решения: статусы БД = varchar+CHECK (ADR-003); celery eager по умолчанию при APP_ENV=test (ADR-013); app/db.session и infra/s3 лениво импортируются из main.py (health-check «skip» до T0.3/T0.5); client-фикстура не зависит от БД/S3 (развязка тикетов).
- Тесты: `pytest tests/api/test_health.py tests/unit/test_config.py` → 5 passed; uvicorn smoke: `python -m uvicorn app.main:app` → GET /health = 200 {"status":"ok","version":"0.1.0",checks:{db,redis,s3}} (uvicorn лог приложен в чат).
- Статус: DONE.

### T0.3 — SQLAlchemy 2.x + Alembic + base models — DONE (2026-09-20)
- Файлы: app/db/{__init__,base,session}.py; app/models/{video,clip,job,rendered_asset,platform_account,publication}.py; alembic/{alembic.ini,env.py,script.py.mako,versions/0001_initial.py}; tests/unit/{test_migrations,test_models}.py; PRAGMA foreign_keys=ON для SQLite в init_engine (иначе FK не проверялись бы).
- Решения: FK-политики по ADR-FK (clips→videos RESTRICT, rendered_assets→clips CASCADE, publications→clips RESTRICT / →assets SET NULL / →accounts RESTRICT); partial unique uq_publications_active (clip_id,platform) WHERE status NOT IN (cancelled,failed); CheckConstraint имена в миграциях передаются короткими (`name="status"`), т.к. alembic применяет convention `ck_%(table)s_%(constraint_name)s` (нашёл через parity-тест); явный `from sqlalchemy.dialects import postgresql` в моделях (нашёл через прямой импорт: скрытая зависимость от порядка импортов).
- Тесты: `pytest tests/` → **22 passed**: upgrade head/-1/up; паритет «миграции ↔ Base.metadata» (колонки/уникальные/индексы/FK/CHECK); CHECK-статусы; FK RESTRICT/CASCADE/SET NULL; partial unique; idempotency unique; defaults.
- Статус: DONE.

### T0.4 — Celery/Redis foundation + Job wiring — DONE (2026-09-20)
- Файлы: app/infra/queue.py (Celery app, eager при APP_ENV=test/CELERY_TASK_ALWAYS_EAGER — ADR-013), app/workers/{celery_app,tasks}.py (ping), app/schemas/{__init__,common,job}.py, app/api/v1/jobs.py (GET /api/v1/jobs/{id}), tests/api/test_jobs.py.
- Решения: DateTimeUtc — сериализация дат ISO8601 с Z через PlainSerializer; JobRead.type читается из ORM-атрибута job_type (validation_alias).
- Тесты: `pytest tests/` → **27 passed**: GET job 200/404/422(validation_error, единый формат), eager ping → "pong", celery conf eager=True. Живой Redis не требуется (DoD «с живым Redis — тоже или SKIP» → в песочнице нет Redis: eager-режим подтверждён, реальный broker-коннект — scripts/verify_db_redis.py на реальной машине).
- Статус: DONE.
