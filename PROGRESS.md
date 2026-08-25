# PROGRESS.md

Единственная долгосрочная память проекта между сессиями Codex. Правила:
- Одна строка на значимый шаг: дата, что сделано, что дальше.
- Без кода и объяснений внутри — только факты.
- Обновляется только после завершения значимого шага, при обнаружении существенного блокера или при изменении текущего Stage.
- Текущий этап (см. AGENTS.md, раздел 6) держится в самом верху и обновляется только при смене Stage.
- Не превращать файл в журнал мелких действий и не записывать намерения перед началом работы.

---

## Текущий этап
`Этап 0 — Скелет` (в работе)

## Лог

- 2026-08-25 — Создан AGENTS.md, ARCHITECTURE.md, CONTRACTS.md, PROGRESS.md. Кодовой базы ещё нет. Следующий шаг: структура папок по модулям и базовая схема БД (Этап 0).
- 2026-08-25 — Синхронизирована проектная документация перед стартом Этапа 0: структура `backend/app/`, naming, правила `PROGRESS.md`, Stage 1 pipeline и базовые доменные сущности. Следующий шаг: старт Этапа 0.
- 2026-08-25 — Stage 0.1 завершён: создан repository skeleton и минимальный FastAPI backend с `/health`; тест health endpoint проходит. Следующий шаг: Stage 0.2 database foundation.
- 2026-08-25 — Stage 0.2 завершён: создан SQLAlchemy foundation для core domain entities, DATABASE_URL вынесен в окружение, model metadata/FK тесты проходят без PostgreSQL. Следующий шаг: Stage 0.3 — Alembic.
- 2026-08-25 — Stage 0.3 завершён: Alembic подключён к существующей SQLAlchemy metadata, создана первая revision для core domain tables, offline SQL generation и тесты проходят. Следующий шаг: Stage 0.4 — Redis/Celery skeleton.
- 2026-08-25 — Stage 0.4 завершён: создан Celery foundation с Redis broker/backend через env, техническая health task зарегистрирована и проходит eager tests без Redis. Следующий шаг: Stage 0.5 — storage abstraction + MinIO config.
- 2026-08-25 — Stage 0.5 завершён: создан S3-compatible storage abstraction на boto3 с env-конфигурацией для MinIO/S3, unit tests проходят без сети. Следующий шаг: Stage 0.6 — frontend skeleton.
