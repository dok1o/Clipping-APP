# PROGRESS.md — журнал Stage/тикетов

> Приоритет: MASTER_SPEC > CONTRACTS > ARCHITECTURE > AGENTS > KNOWLEDGE > **PROGRESS**.
> PROGRESS фиксирует факты и статусы; никогда не противоречит SPEC/контрактам.

## Текущий этап

`Stage 0 — Documentation, skeleton, health, DB, Celery, S3, frontend, audit` (in progress)

---

## Решения/блокеры (top)

- **2026-09-20 (T0.1)**: В репозитории обнаружена частичная реализация предыдущего (Codex) промпта (коммит e3b2d9f «feat: add vertical clip rendering flow») с неканонической структурой (`app/ingestion|video_effects|...`, без `/api/v1`, без Job/PlatformAccount/Publication по §8, без MASTER_SPEC). Решение: пересборка по канону §5 с нуля; старый код сохранён в git-истории, история не переписывалась. ADR-000 в ARCHITECTURE.md. Файл `docs/codex-master-prompt-ai-clipper.md` (документ пользователя) сохранён.
- **2026-09-20 (T0.1)**: Sandbox-ограничения (см. docs/KNOWLEDGE.md §1): нет ffmpeg/ffprobe, нет Docker/PG/Redis/MinIO, нет GPU. Стратегия: основной pytest-сьют на SQLite+moto+Celery-eager; реальные проверки — scripts/verify_*.py с честным SKIP + список проверок на реальной машине в README.
- **2026-09-20 (решение пользователя до T1.4)**: первая платформа — **TikTok** (Content Posting API); YouTube — вторая, подключается позже без рефакторинга ядра (интерфейс Publisher). Выбор дан пользователем заранее, остановка перед T1.4 снята; далее работа полностью автономна.

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

### T0.5 — S3 abstraction + crypto — DONE (2026-09-20)
- Файлы: app/infra/s3.py (S3Storage: ensure_bucket/head_bucket/upload_file/upload_fileobj/download_to_file/get_object_bytes/exists/delete_object/presigned_get; boto3 только здесь), app/infra/crypto.py (реэкспорт core/security, ADR-008), tests/unit/{test_s3,test_crypto,test_audit_rules}.py.
- Решение (факт в KNOWLEDGE §6): moto 5.2.3 `mock_aws` НЕ перехватывает клиентов с кастомным endpoint_url (реальный сетевой запрос к хосту) → тесты используют in-process moto HTTP-сервер (moto[server], flask) на 127.0.0.1:random_port — boto3 exercised полностью, включая path-style addressing.
- Тесты: `pytest tests/` → **43 passed**: S3 roundtrip (upload/download/bytes/exists/delete/presigned/ensure_bucket idempotent), Fernet roundtrip + tamper + missing key + маскировка + реэкспорт, аудит-правила (boto3 только в infra/s3.py; нет shell=True/os.system; нет create_all в app; нет секретоподобных литералов).
- Статус: DONE.

---

## Stage 0 — REPORT (2026-09-20)

**Изменения**: 6 канонических доков + README + .env.example (60+ env, секреты пустые) + .gitignore; backend: pyproject (extras dev/whisper/ml), app/core (config/logging/errors/security), app/db (base/session), app/models (6 таблиц §8), alembic (env + 0001 миграция), app/infra (queue, s3, crypto), app/workers (celery_app, tasks.ping), app/schemas (common, job), app/api/v1 (router, jobs), tests (unit/api, conftest: per-test sqlite через alembic-шаблон + in-process moto S3 HTTP-сервер); frontend: Vite+React+TS+Tailwind, App+навбар+4 заглушки, api.ts (fetch, ApiError с detail.code), dev-прокси /api→8000.

**Структура**: каноническое дерево §5 (проверено тестом test_repo_structure).

**Зависимости**: fastapi, uvicorn[standard], sqlalchemy 2.x, alembic, pydantic+pydantic-settings, celery[redis], redis, boto3, python-multipart, cryptography, psycopg[binary], httpx; dev: pytest, moto[s3,server] (in-process HTTP-сервер для честного тестирования кастомного endpoint_url), flask (транзитивно moto[server]). Frontend: react 18, react-router-dom 6, tailwindcss 3, vite 5. Все — open-source, фиксация в pyproject/package.json.

**Тесты**: `pytest -m "not real_services"` → **43 passed**; `alembic upgrade head → downgrade -1 → upgrade head` → OK (sqlite); `npm run build` (tsc+vite) → OK; `pip check` → OK; secrets/artifacts greps → CLEAN; CORS на FRONTEND_ORIGIN покрыт тестом.

**Git status**: clean (после коммитов; только untracked логи/кэш вне git).

**Diff summary**: e3b2d9f→HEAD: полная пересборка (старая неканоническая реализация удалена, сохранена в истории).

**Блокеры/ограничения**: нет ffmpeg/ffprobe, Docker/PG/Redis/MinIO, GPU в песочнице → реальные проверки перенесены на машину пользователя (README «Проверки на реальной машине», scripts/verify_*.py по Stage). Живой Redis для Celery проверен только eager-режимом (unit) — broker-коннект проверить на реальной машине (scripts/verify_db_redis.py).

**GATE: GO** — /health 200; миграции туда-обратно зелёные; полный suite зелёный без внешних сервисов; frontend build ok; greps чисты; доки консистентны.

---
