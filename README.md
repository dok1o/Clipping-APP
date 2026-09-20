# AI Clipper

Локальный self-hosted AI Clipper: длинное видео → вертикальные клипы 1080x1920 для YouTube Shorts / TikTok с заголовками, описаниями, хэштегами, субтитрами → публикация вручную/по расписанию → метрики через официальные API → самообучение на лучших моментах.

Стек: FastAPI + SQLAlchemy 2 + Alembic + Celery/Redis + PostgreSQL + MinIO (S3) + ffmpeg + faster-whisper + локальная LLM; фронтенд React+Vite+Tailwind. Только open-source, нулевой бюджет, single-user.

## Документы

- `docs/MASTER_SPEC.md` — главный спек (видение, UC-1..9, Stage-объём)
- `CONTRACTS.md` — сущности, БД-правила, API-контракты
- `ARCHITECTURE.md` — модули, границы, ADR
- `AGENTS.md` — правила работы агента, команды, запреты
- `docs/KNOWLEDGE.md` — проверенные факты (URL доков платформ, лимиты, sandbox-ограничения)
- `PROGRESS.md` — журнал Stage/тикетов

## Quickstart (с нуля)

```bash
# 0) окружение
python3 -m venv .venv
cp .env.example .env
# сгенерируй ключ шифрования и вставь в .env (ENCRYPTION_KEY=...):
./.venv/bin/python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

# 1) зависимости бэкенда
cd backend && PIP_CACHE_DIR=/home/user/pipcache ../.venv/bin/pip install -e ".[dev,ml]" && cd ..
# ml-экстра (scikit-learn+lightgbm+joblib) нужна для Stage 7 (ML-rerank); без неё — эвристика

# 2) сервисы (на реальной машине; в песочнице их нет — тесты идут на SQLite/moto/eager):
#    PostgreSQL: docker run -d -p 5432:5432 -e POSTGRES_USER=clipper -e POSTGRES_PASSWORD=clipper -e POSTGRES_DB=clipper postgres:16
#    Redis:      docker run -d -p 6379:6379 redis:7
#    MinIO:      docker run -d -p 9000:9000 -p 9001:9001 -e MINIO_ROOT_USER=clipper -e MINIO_ROOT_PASSWORD=clipper-minio minio/minio server /data --console-address ":9001"
#    (в .env: S3_ACCESS_KEY=clipper, S3_SECRET_KEY=clipper-minio)
#    Для быстрого старта без сервисов можно использовать SQLite: DATABASE_URL=sqlite:///./clipper-dev.db

# 3) миграции
cd backend && ../.venv/bin/alembic upgrade head && cd ..

# 4) API
cd backend && ../.venv/bin/python -m uvicorn app.main:app --reload --port 8000 &
#    (без Redis: CELERY_TASK_ALWAYS_EAGER=1 ../.venv/bin/python -m uvicorn app.main:app --port 8000)

# 5) Celery worker (для фоновых задач; опционально при eager-режиме)
cd backend && ../.venv/bin/celery -A app.workers.celery_app worker --loglevel=info &

# 6) фронтенд
cd frontend && npm install && npm run dev   # http://localhost:5173
```

## Тесты и проверки

```bash
# основной suite — без внешних сервисов (SQLite + moto + Celery eager):
cd backend && ../.venv/bin/pytest -m "not real_services"

# реальные интеграционные (живые PG/Redis/MinIO/ffmpeg):
cd backend && RUN_REAL_INTEGRATION=1 ../.venv/bin/pytest -m real_services

# runtime-проверки окружения (честные PASS/FAIL/SKIP):
./.venv/bin/python scripts/verify_ffmpeg.py      # синтетика + вертикальный рендер 1080x1920
./.venv/bin/python scripts/verify_s3.py          # MinIO/S3 roundtrip (нужны ключи)
./.venv/bin/python scripts/verify_db_redis.py    # PostgreSQL + Redis connectivity
```

### Проверки, которые нужно выполнить на реальной машине (GPU/ffmpeg/ключи)

В песочнике разработки нет ffmpeg, GPU, живых PG/Redis/MinIO и платформенных ключей, поэтому там эти проверки дают SKIP и покрываются моками. На целевой машине:

1. `./.venv/bin/python scripts/verify_ffmpeg.py` → PASS (рендер 1080x1920 H.264+AAC).
2. `./.venv/bin/python scripts/verify_db_redis.py` → PASS.
3. `./.venv/bin/python scripts/verify_s3.py` → PASS (MinIO запущен, ключи в .env).
4. Stage 1.4+: `./.venv/bin/python scripts/verify_platform.py --dry-run` → PASS (ключи платформы в .env).
5. Stage 3: `./.venv/bin/python scripts/verify_whisper.py` → PASS (GPU/CPU транскрипция синтетики).

## Структура

См. `ARCHITECTURE.md` §2. Кратко: `backend/app/{core,db,models,schemas,api,services,infra,workers}`, `backend/alembic/`, `backend/tests/{unit,api,integration}`, `frontend/src/{pages,components}`, `scripts/`, `storage/`.
