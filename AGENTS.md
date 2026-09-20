# AGENTS.md — как работать агенту в этом репозитории

> Приоритет документов: MASTER_SPEC > CONTRACTS > ARCHITECTURE > **AGENTS** > KNOWLEDGE > PROGRESS.
> В начале каждого Stage перечитай: PROGRESS, ARCHITECTURE, CONTRACTS, docs/MASTER_SPEC, docs/KNOWLEDGE, AGENTS + `git status` + `git diff --stat`.

## Роли
- **Director**: порядок Stage, DoD, acceptance gates, отсутствие регрессий, аудит.
- **Manager**: CONTRACTS/ARCHITECTURE, границы модулей, тикеты (разрешённые файлы, запреты, DoD).
- **Worker**: минимальный чистый код под тикет, тесты с выводом, без gold-plating.

## Окружение

- Python — только через `.venv` в корне репо. Node — только внутри `frontend/`.
- В песочнице Arena `.venv/` и `node_modules/` не переживают перезапуск сессии — восстановление:
  ```bash
  python3 -m venv .venv
  PIP_CACHE_DIR=/home/user/pipcache ./.venv/bin/pip install -e ".[dev]"   # из backend/
  cd frontend && npm_config_cache=/home/user/npmcache npm install
  ```

## Стандартные команды

```bash
# --- bootstrap ---
python3 -m venv .venv
cd backend && PIP_CACHE_DIR=/home/user/pipcache ../.venv/bin/pip install -e ".[dev]"

# --- тесты (основной suite, без внешних сервисов) ---
cd backend && ../.venv/bin/pytest -m "not real_services"

# --- реальные интеграционные проверки (нужны живые сервисы/бинари) ---
cd backend && RUN_REAL_INTEGRATION=1 ../.venv/bin/pytest -m real_services

# --- миграции ---
cd backend && ../.venv/bin/alembic upgrade head
cd backend && ../.venv/bin/alembic downgrade -1 && ../.venv/bin/alembic upgrade head

# --- запуск API (dev) ---
cd backend && ../.venv/bin/python -m uvicorn app.main:app --reload --port 8000

# --- celery worker (нужен Redis; без Redis — CELERY_TASK_ALWAYS_EAGER=1) ---
cd backend && ../.venv/bin/celery -A app.workers.celery_app worker --loglevel=info

# --- frontend ---
cd frontend && npm install && npm run build && npm run typecheck && npm run dev

# --- runtime-verify скрипты (честные PASS/FAIL/SKIP) ---
./.venv/bin/python scripts/verify_ffmpeg.py
./.venv/bin/python scripts/verify_s3.py
./.venv/bin/python scripts/verify_db_redis.py
```

## Структура
Канон — см. ARCHITECTURE.md §2 и MASTER_SPEC. Ключевое: `api/` — только HTTP; `services/` — бизнес-логика по доменам; `infra/s3.py` — единственный boto3; `services/render/ffmpeg_runner.py` — единственный subprocess ffmpeg/ffprobe; `workers/tasks.py` — тонкие таски.

## Запреты (нарушение = провал Stage)
1. Hardcoded credentials/токены/ключи в коде/доках/тестах (только env; fake-значения в тестах допустимы).
2. `boto3` вне `app/infra/s3.py` (проверяется тестом `test_audit_rules.py`).
3. `shell=True`, `os.system`, строковые shell-команды с интерполяцией (проверяется тестом).
4. `create_all` в прод-коде (миграции — только Alembic; `create_all` — только в тесте сравнения схем).
5. Коммитить: `.env`, `.venv/`, `storage/*` (кроме `.gitkeep`), медиа, `*.bin/*.pt/*.joblib/*.onnx`, `node_modules/`, `dist/`, модели, большие файлы.
6. Destructive git: `push --force`, `reset --hard`, `clean -fd`, `rebase -i` на чужих ветках. Работаем в текущей ветке, атомарные коммиты.
7. Платформенные API — только по официальной документации (URL + дата проверки в docs/KNOWLEDGE.md). Не выдумывать эндпоинты. Никакого скрапинга.
8. Платные SaaS/API в обязательном пути. Платный LLM API — не часть системы.
9. Заявлять «готово/работает» без фактического прогона команды и вывода. Ограничения sandbox фиксировать честно (PASS/SKIP/FAIL).

## Workflow тикета
1. Прочитать DoD тикета; зафиксировать разрешённые файлы/запреты (Manager).
2. Если меняется поведение/API/схема — сначала CONTRACTS.md (+ MASTER_SPEC/ARCHITECTURE), затем код.
3. Реализация (Worker) → тесты → прогон с выводом.
4. Обновить PROGRESS.md (статус, тесты, файлы, решения).
5. Атомарный коммит: `stage{N}-t{N.M}: краткое описание`.

## Отчёт по Stage (формат §30, в чат + PROGRESS.md)
```
## Stage N — REPORT
Изменения / Структура / Зависимости / Тесты (команды+выводы) / Git status / Diff summary / Блокеры / GATE: GO|NO-GO
```
