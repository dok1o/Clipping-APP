# PROGRESS.md

Единственная долгосрочная память проекта между сессиями Codex. Правила:
- Одна строка на значимый шаг: дата, что сделано, что дальше.
- Без кода и объяснений внутри — только факты.
- Обновляется только после завершения значимого шага, при обнаружении существенного блокера или при изменении текущего Stage.
- Текущий этап (см. AGENTS.md, раздел 6) держится в самом верху и обновляется только при смене Stage.
- Не превращать файл в журнал мелких действий и не записывать намерения перед началом работы.

---

## Текущий этап
`Stage 1 — MVP without AI` (in progress)

## Лог

- 2026-08-25 — Создан AGENTS.md, ARCHITECTURE.md, CONTRACTS.md, PROGRESS.md. Кодовой базы ещё нет. Следующий шаг: структура папок по модулям и базовая схема БД (Этап 0).
- 2026-08-25 — Синхронизирована проектная документация перед стартом Этапа 0: структура `backend/app/`, naming, правила `PROGRESS.md`, Stage 1 pipeline и базовые доменные сущности. Следующий шаг: старт Этапа 0.
- 2026-08-25 — Stage 0.1 завершён: создан repository skeleton и минимальный FastAPI backend с `/health`; тест health endpoint проходит. Следующий шаг: Stage 0.2 database foundation.
- 2026-08-25 — Stage 0.2 завершён: создан SQLAlchemy foundation для core domain entities, DATABASE_URL вынесен в окружение, model metadata/FK тесты проходят без PostgreSQL. Следующий шаг: Stage 0.3 — Alembic.
- 2026-08-25 — Stage 0.3 завершён: Alembic подключён к существующей SQLAlchemy metadata, создана первая revision для core domain tables, offline SQL generation и тесты проходят. Следующий шаг: Stage 0.4 — Redis/Celery skeleton.
- 2026-08-25 — Stage 0.4 завершён: создан Celery foundation с Redis broker/backend через env, техническая health task зарегистрирована и проходит eager tests без Redis. Следующий шаг: Stage 0.5 — storage abstraction + MinIO config.
- 2026-08-25 — Stage 0.5 завершён: создан S3-compatible storage abstraction на boto3 с env-конфигурацией для MinIO/S3, unit tests проходят без сети. Следующий шаг: Stage 0.6 — frontend skeleton.
- 2026-08-25 — Stage 0.6 завершён: создан минимальный Vite React + Tailwind frontend skeleton, production build проходит, backend tests не сломаны. Следующий шаг: Stage 0 final audit / integration verification.
- 2026-08-25 — Stage 0 завершён: skeleton, FastAPI, SQLAlchemy models, Alembic migration, Celery, S3 storage abstraction и React/Tailwind frontend verified. Следующий шаг: Stage 1 — MVP without AI.
- 2026-08-25 — Stage 1.1 завершён: реализован manual video upload через `POST /videos`, Video record создаётся через DB session, файл проходит через storage abstraction, `GET /videos/{id}` и backend tests проходят. Следующий шаг: Stage 1.2 — manual clip creation by timestamps.
- 2026-08-25 — Stage 1.2 завершён: реализовано ручное создание Clip по timestamps через `POST /videos/{video_id}/clips`, metadata endpoints `GET /clips/{clip_id}` и `GET /videos/{video_id}/clips`, backend tests проходят. Следующий шаг: Stage 1.3 — vertical render with ffmpeg.
- 2026-08-25 — Stage 1.3 завершён: реализован синхронный vertical render через `POST /clips/{clip_id}/render`, source/output проходят через storage abstraction, создаётся RenderedAsset, Clip status обновляется, backend tests проходят. Следующий шаг: Stage 1.4 — first-platform publication preparation.
