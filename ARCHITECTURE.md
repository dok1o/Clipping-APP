# ARCHITECTURE — модули, границы, потоки, ADR

> Приоритет: MASTER_SPEC > CONTRACTS > **ARCHITECTURE** > AGENTS > KNOWLEDGE > PROGRESS.

## 1. Обзор

```
┌────────────┐   HTTP/JSON    ┌──────────────────────────────────────────┐
│  frontend  │ ─────────────► │  FastAPI app (app/main.py)               │
│ React/Vite │ ◄───────────── │  api/v1/* — только HTTP-слой             │
└────────────┘                │  services/* — бизнес-логика              │
                              │  models/schemas — домен                  │
                              │  infra/* — s3 (boto3), queue (Celery)    │
                              └──────┬───────────┬───────────┬───────────┘
                                     │ SQLAlchemy │ Celery    │ boto3
                                     ▼           ▼           ▼
                                PostgreSQL     Redis      MinIO/S3
                                              (broker/    (videos/,
                                               backend)    renders/)
                              workers/* — Celery tasks → services/*
                              ffmpeg/ffprobe — только через
                              services/render/ffmpeg_runner.py
```

Runtime-компоненты: FastAPI (uvicorn), Celery worker, Celery beat (Stage 5), PostgreSQL, Redis, MinIO, frontend dev/build. Все конфигурируются env (см. `.env.example`).

## 2. Структура и границы модулей

```
backend/app/
├── main.py            # FastAPI app factory, /health, CORS, error handlers
├── core/              # config (pydantic-settings), logging, errors (AppError), security (Fernet)
├── db/                # session (engine/sessionmaker, init_engine для тестов), base (DeclarativeBase+naming)
├── models/            # SQLAlchemy ORM, 1 файл на домен
├── schemas/           # Pydantic request/response, 1 файл на домен
├── api/               # deps (get_settings/get_db/get_storage) + v1/ роутеры
├── services/          # бизнес-логика по доменам:
│   ├── ingest/        #   upload_service — стриминг, санитизация, S3, ffprobe(Video)
│   ├── clips/         #   clip_service — manual clip, timestamp-валидация
│   ├── render/        #   ffmpeg_runner (ЕДИНСТВЕННЫЙ subprocess ffmpeg/ffprobe) + render_service
│   ├── transcription/ #   whisper_service, scene_service (Stage 3)
│   ├── ai_clipping/   #   features, heuristic_ranker, ml_ranker (Stage 3/7)
│   ├── text_gen/      #   base (Provider), local_provider, fake_provider, text_service (Stage 2)
│   ├── publish/       #   base (Publisher), youtube/tiktok адаптеры, publish_service (Stage 1.4)
│   ├── analytics/     #   metrics_service (Stage 6)
│   └── ml/            #   dataset, train, evaluate (Stage 7)
├── infra/             # s3.py (ЕДИНСТВЕННЫЙ boto3), queue.py (Celery app), crypto.py (re-export)
└── workers/           # celery_app.py (CLI entry), tasks.py — тонкие таски → services
```

Правила:
- `api/*` — только HTTP: валидация, статусы, вызов сервиса, маппинг ошибок. Никакого ffmpeg/boto3/SQL.
- `services/*` — бизнес-логика; кросс-доменные импорты только через явные интерфейсы (исключение: `ffmpeg_runner.probe_media` используется ingest — это единая точка ffprobe, см. ADR-005).
- `infra/s3.py` — единственное место boto3 (проверяется тестом `test_audit_rules`).
- `workers/tasks.py` — тонкие обёртки: Job-обновления + вызов сервиса.
- Тяжёлые ML-зависимости (faster-whisper, scikit-learn) — optional extras `[whisper]`/`[ml]` с lazy import (ADR-010).

## 3. Потоки данных

### Upload (UC-1)
`multipart → стрим чанками 1MB → tmp file (лимит байт → 413) → S3 upload_file → ffprobe(tmp) опц. → Video ready`.
Строка Video создаётся со статусом `uploading` до S3-загрузки; при storage-ошибке → `failed` + 500 `storage_error`.

### Manual clip (UC-2)
`POST → clip_service (проверки без ffprobe: start≥0, end>start, 5..180с, end≤duration если известна) → Clip draft`.

### Render (UC-3)
`POST /clips/{id}/render → Job(queued, type=render) + Clip render_queued → Celery task →
job running → clip rendering → download video из S3 в tmp → ffmpeg_runner.render_vertical →
upload renders/{clip}/{asset}.mp4 → RenderedAsset ready + clip rendered + job succeeded |
RenderError → clip render_failed + job failed (код + stderr tail)`.
Stage 1: eager-режим допустим (контракт 202 стабилен); Stage 5 — полный Celery.

## 4. Очереди

- Celery app в `infra/queue.py`; broker/backend = Redis (env). `CELERY_TASK_ALWAYS_EAGER=1` (или APP_ENV=test) — синхронное выполнение без Redis (dev/тесты).
- Job lifecycle: `queued → running → succeeded|failed`, `retrying` при retry (Stage 5: retry только для идемпотентных; publish — никогда автоматически без idempotency-проверки).
- Stage 5 (реализовано): `workers/job_lifecycle.py` — общий lifecycle задач (running/succeeded/failed/retrying, backoff 2^n×60с, retry только идемпотентных); `reconcile_stuck_jobs` на старте воркера (worker_ready) + POST /api/v1/jobs/reconcile; Beat 30с `process_scheduled_publications`; ADR-015: защита от двойной публикации — атомарный DB-переход scheduled→uploading (rowcount) + external_post_id guard вместо Redis SET NX (Redis отсутствует в dev/тестах; lock надстраивается в проде).

## 5. Хранилище

- S3-совместимое (MinIO локально / любой S3 через env). Бакет `clipper` (env).
- Ключи: `videos/{video_uuid}/{safe_name}`, `renders/{clip_id}/{asset_id}.mp4`, далее `models/…` (Stage 7).
- Скачивание — presigned URL (900 сек) через `infra/s3.py`.

## 6. ADR (Architecture Decision Records)

- **ADR-000 (repo)**: в репозитории находилась частичная реализация предыдущего (Codex) промпта с неканонической структурой (`app/ingestion`, `app/video_effects`, …) — удалена в рамках T0.1, сохранена в git-истории (коммит e3b2d9f). Причина: мастер-промпт требует каноническую структуру §5 «создай именно её».
- **ADR-001 sync SQLAlchemy**: sync ORM вместо async — Celery-воркеры синхронны, тесты проще; sync-эндпоинты FastAPI исполняются в threadpool. Альтернатива (async) — сложность без выигрыша для локального single-user приложения.
- **ADR-002 переносимость СУБД**: типы `sa.Uuid()`, `JSON().with_variant(JSONB)`, `DateTime(timezone=True)` дают PG-семантику в проде и работают на SQLite в тестах без ветвлений.
- **ADR-003 статусы varchar+CHECK**: единый стиль на PG/SQLite, простые миграции; в коде строковые константы-классы, в Pydantic `Literal` (native PG enum отвергнут из-за ALTER-сложностей).
- **ADR-004 init_engine**: движок инициализируется лениво, `init_engine(url)`/`reset_engine()` для изоляции тестов и eager-Celery задач, использующих ту же фабрику сессий.
- **ADR-005 ffprobe-шлюз**: `ffmpeg_runner.probe_media` используется и `ingest` (разрешено §11), т.к. ffmpeg_runner — единственная точка запуска медиа-бинарей (запрет §6 касается не модуля, а subprocess-вызовов).
- **ADR-006 render через Job**: контракт 202+job_id стабилен; Stage 1 — eager (`.delay()` при `task_always_eager` выполняется синхронно в процессе), Stage 5 — без изменения контракта.
- **ADR-007 S3-абстракция**: весь доступ через `S3Storage` (boto3 только там); тесты — moto; скачивание — presigned.
- **ADR-008 crypto**: реализация Fernet в `core/security.py`; `infra/crypto.py` — реэкспорт (нет дублирования, §9).
- **ADR-009 frontend**: Vite+React+TS+Tailwind v3 + `react-router-dom` (функциональная навигация, не UI-библиотека); без MUI/antd/framer-motion, без лендинга.
- **ADR-010 ML-зависимости**: faster-whisper/scikit-learn — optional extras (`[whisper]`, `[ml]`), lazy import в сервисах; основной pytest-сьют не требует их установки (моки), реальные проверки — `scripts/verify_*.py` + `tests/integration` (маркер `real_services`).
- **ADR-011 ошибки**: `AppError(status, code, message, fields)` + единые exception handlers; 422 `validation_error` для pydantic-ошибок, доменные коды для бизнес-ошибок.
- **ADR-012 end>start в сервисе**: `end_sec > start_sec` проверяется в clip_service (400 `invalid_range`), а не в pydantic model_validator — чтобы вернуть 400 из §10 вместо 422.
- **ADR-013 celery eager по умолчанию в test**: `celery_eager_by_default` = APP_ENV=test или env CELERY_TASK_ALWAYS_EAGER; основной сьют не требует живого Redis.
- **ADR-014 пип-кэш в песочнице**: `.venv/` и `node_modules/` не переживают перезапуск песочницы → используем PIP_CACHE_DIR=/home/user/pipcache и npm_config_cache=/home/user/npmcache для быстрого восстановления (см. KNOWLEDGE).
