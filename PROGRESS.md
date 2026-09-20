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
