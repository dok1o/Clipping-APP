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

### T1.1 — Upload + Video — DONE (2026-09-20)
- Файлы: app/services/render/ffmpeg_runner.py (probe_media — единственная точка ffprobe; бинаррь отсутствует → metadata null, upload не падает), app/services/ingest/upload_service.py (санитизация, ключ videos/{uuid}/{safe_name}, stream 1MB-чанками → tmp → S3, Content-Length precheck 413, лимит на лету, mime+ext allowlist), app/schemas/video.py, app/api/v1/videos.py (POST 201 / GET list / GET by id), api/deps.get_storage.
- Отступление от списка файлов тикета (зафиксировано): ffmpeg_runner.py создан в T1.1 с probe_media, т.к. §11 разрешает ffprobe для Video, а §6 требует единственную точку запуска бинарей — правило §6 приоритетнее (ADR-005).
- Тесты: unit sanitize/keys/415/413/empty (12) + api multipart 201 (S3 mock содержит ключ, status ready, duration null без ffprobe) / 415 / 400 / 413 (settings override) / 500 storage_error (Video→failed) / пагинация / 404 / 422 → все зелёные; полный suite 65 passed.
- Статус: DONE.

### T1.2 — Manual Clip — DONE (2026-09-20)
- Файлы: app/services/clips/clip_service.py (timestamp-валидация: end>start → 400 invalid_range, 5..180с из конфига, end≤duration только если duration известна; НИКАКИХ медиа-бинарей), app/schemas/clip.py, app/api/v1/clips.py (POST /videos/{id}/clips/manual, GET /clips?video_id=, GET /clips/{id}).
- Тесты: 13 API-тестов (201; границы 5.0/4.99, 180/180.01; end≤start; video_not_ready 409; duration known vs null; title 1..140; 404/422; list) + mock-ассерт «probe_media не вызывается» + audit-grep «clip_service не ссылается на ffmpeg/subprocess». Полный suite: **79 passed**.
- Статус: DONE.

### T1.3 — Vertical render + runtime verify — DONE (2026-09-20)
- Файлы: ffmpeg_runner.py дополнен (VERTICAL_FILTER, build_render_args: -ss ДО -i, -t после, libx264 veryfast crf23, aac 128k, yuv420p, faststart, -r 30; render_vertical с RenderError-кодами ffmpeg_missing/render_timeout/render_failed/invalid_timestamps, stderr-хвост ≤2KB), app/services/render/render_service.py (queue_render с идемпотентностью: rendered+asset → тот же succeeded job; queued/rendering → 409; rendered без asset → 422; retry после fail; execute_render_job: lifecycle clip+job+asset, S3 download/upload), app/schemas/rendered_asset.py, app/api/v1/{renders,clips render endpoint}.py, app/workers/tasks.py (render_task тонкая обёртка), scripts/verify_ffmpeg.py (PASS/FAIL/SKIP + fallback-зонд через ffmpeg -i), tests/unit/test_ffmpeg_runner.py, tests/api/test_render.py, tests/integration/test_real_render.py.
- Реальные проверки (не моки!): `verify_ffmpeg.py` → **PASS** (ffmpeg 7.0.2 из imageio-ffmpeg): выход 1080x1920/h264/aac/yuv420p/faststart. `RUN_REAL_INTEGRATION=1 pytest tests/integration` → **1 passed** — полный e2e: upload настоящего mp4 → manual clip → render через API (Celery-eager worker) → RenderedAsset ready → presigned download → валидный MP4 (ftyp).
- Тесты мок-уровня: args/порядок/фильтр, timeout/missing-binary/nonzero-exit/empty-output/invalid-timestamps, lifecycle + идемпотентность + 409 + retry-after-fail, presigned. Полный suite: **93 passed** (not real_services) + 1 real integration PASS.
- Статус: DONE.

### T1.4 — Ручная публикация TikTok (платформа выбрана пользователем) — DONE (2026-09-20)
- Исследование официальных доков выполнено ДО реализации (§0.8): 3 официальные страницы TikTok Content Posting API (direct-post, status/fetch, creator_info) — URL + дата + ограничения в docs/KNOWLEDGE.md §2. Выбор: FILE_UPLOAD (self-hosted, публичного верифицированного URL нет); privacy-маппинг public/unlisted/private → PUBLIC_TO_EVERYONE/MUTUAL_FOLLOW_FRIENDS/SELF_ONLY.
- Файлы: app/services/publish/{base,tiktok,publish_service}.py (Publisher Protocol + registry; идемпотентность {clip_id}:{platform}:{asset_id}:{sha256(title)[:12]}; Fernet credentials; scheduled_at → scheduled без немедленной публикации), app/schemas/publication.py (+PlatformAccount), app/api/v1/publications.py (+ platform-accounts CRUD-минимум), tests/{fakes.py,unit/test_tiktok_publisher.py,api/test_publications.py}, scripts/verify_platform.py.
- Тесты: адаптер против httpx.MockTransport (init/upload/status flow, Content-Range, privacy_level, error-code propagation, title 2200 лимит); API: 201 published (credentials "***", в БД зашифрованы), 409 duplicate, 502 platform_error → Publication failed + retry разрешён, scheduled без вызова publisher, 404 clip/asset/account, 422 platform mismatch. `scripts/verify_platform.py --dry-run` → PASS; `--real` → SKIP (нет ключей, ожидаемо).
- Полный suite: **109 passed** (not real_services).
- Статус: DONE.

### T1.5 — Аудит Stage 1 — DONE (2026-09-20)
- Secrets/boto3/shell=True/create_all/artifacts greps: CLEAN. Миграции up/-1/up: OK. Real ffmpeg e2e (integration): **1 passed**.
- Статус: DONE.

---

## Stage 1 — REPORT (2026-09-20)

**Изменения**: upload (стрим → S3, валидации 413/415/400, ffprobe-опциональность), manual clip (timestamp-only, без медиа-бинарей — доказано grep+mock), вертикальный рендер 1080x1920 H.264+AAC+yuv420p+faststart через Job lifecycle с идемпотентностью, ручная публикация TikTok через официальный Content Posting API (FILE_UPLOAD), platform-accounts с Fernet, verify-скрипты.

**Тесты**: `pytest -m "not real_services"` → **109 passed**; `RUN_REAL_INTEGRATION=1 pytest tests/integration` → **1 passed** (настоящий ffmpeg e2e: upload→clip→render→download MP4); `scripts/verify_ffmpeg.py` → **PASS** (ffmpeg 7.0.2 из imageio-ffmpeg в песочнице); `scripts/verify_platform.py --dry-run` → **PASS**.

**Блокеры/не проверено в песочнице**: реальная публикация в TikTok (нужны ключи + audited app; `verify_platform.py --real` на машине пользователя); ffprobe-метаданные при загрузке (нет бинаря ffprobe — duration=null по спецификации, на реальной машине с ffprobe заполнится); живой Redis для Celery (eager-режим покрыт тестами).

**GATE: GO** — все эндпоинты §10 работают по контрактам (TestClient-доказательства), render spec соблюдён и подтверждён реальным ffmpeg, публикация на 1 платформу через официальный API (fake+mock+dry-run доказательства + дока по ключам), pytest зелёный, аудит чист.

---

### T2.1+T2.2 — Text gen provider boundary + platform texts + API — DONE (2026-09-20)
- Файлы: app/services/text_gen/{base,fake_provider,local_provider,text_service}.py, app/schemas/text_gen.py, app/api/v1/texts.py, tests/{unit/test_text_gen,api/test_texts}.py.
- Решения: единственный реальный backend — ollama (/api/chat, format=json; OOM → ретрай num_gpu=0 = CPU fallback, unit-покрыто; llamacpp/transformers — честные not_implemented); тексты хранятся в Job(text_gen).result — контракт GET/POST переживёт переход на async в Stage 5; лимиты YouTube(100/5000/500)/TikTok(2200) из официальных доков.
- Тесты: unit 12 (fake детерминирован, markdown-fenced JSON, лимиты платформ, ollama happy/OOM→cpu/unreachable/http-error/stubs) + api 8 (200 с лимитами, youtube vs tiktok, transcript+tone, roundtrip GET, 404/422/502+failed Job). Полный suite: **129 passed**.
- Статус: DONE.

### T2.3 — Аудит Stage 2 — DONE (2026-09-20)
- VRAM-замер: SKIP (нет GPU/ollama в песочнице) — задокументировано в KNOWLEDGE с командами проверки на реальной машине. CONTRACTS §4.12 обновлён реализацией.
- Статус: DONE.

## Stage 2 — REPORT (2026-09-20)
**Изменения**: text_gen домен (provider boundary + fake + ollama + stubs), structured JSON с ретраем, платформенные лимиты, API generate/get, Job-хранение текстов.
**Тесты**: `pytest -m "not real_services"` → **129 passed**.
**Блокеры**: реальный прогон ollama-провайдера — на машине пользователя (команды в KNOWLEDGE §3).
**GATE: GO** — texts API по CONTRACTS, fake зелёный, local конфигурируем, CPU fallback описан и покрыт unit (mock OOM→cpu), pytest зелёный.

---

### T3.1 — faster-whisper транскрипция — DONE (2026-09-20)
- Файлы: app/models/transcript.py + миграция 0002, app/services/transcription/whisper_service.py (extract wav 16k mono через ffmpeg_runner; lazy import faster-whisper (extras [whisper]); device auto→cuda/cpu; CUDA OOM → CPU int8 fallback; device_used в Job result; идемпотентность transcribe:{video_id}), app/schemas/transcription.py, app/api/v1/transcripts.py (POST 202 + GET transcript), workers/tasks.transcribe_task.
- Тесты: unit 6 (device resolution, compute fallback, not-installed, happy-path mocked, CUDA-OOM→CPU mocked) + api 5 (202+segments saved, cached idempotency, 404, failed job при ffmpeg_missing, empty transcript). 
- Статус: DONE.

### T3.2 — Scene detection — DONE (2026-09-20)
- Выбор: ffmpeg select gt(scene,0.4)+showinfo (ADR: без OpenCV/PySceneDetect); fallback равномерные окна 30с; границы в features кандидатов.
- Тесты: unit fallback-границы; **реальный integration**: двухсценная синтетика, ffmpeg 7.0.2 нашёл разрез ~4с (3 passed: e2e render + 2 scene теста).
- Статус: DONE.

### T3.3 — Heuristic ai_clipping — DONE (2026-09-20)
- Файлы: app/models/clip_candidate.py (+миграция 0002), app/services/ai_clipping/{features,heuristic_ranker,candidate_service}.py, app/schemas/ai_clipping.py, app/api/v1/candidates.py.
- Реализовано §18: окна 15/30/45/60 шаг 5с; фичи speech_ratio/key_phrases(RU+EN в features.py)/tempo WPM bell 120-180/loudness RMS(audioop stdlib)/position(интро)/scene_alignment(±2с); веса AI_WEIGHTS_*; NMS IoU>0.5; top_k; POST candidates (регенерация заменяет), GET, POST promote → Clip draft.
- Тесты: unit 12 (фичи детерминированы, IoU, NMS, веса конфигурируются, fallback) + api 7 (top_k, детерминизм, transcript_missing 409, promote→Clip, scene_fallback). Полный suite: **160 passed** + chain-тест gate.
- Статус: DONE.

### T3.4 — Аудит Stage 3 — DONE (2026-09-20)
- Веса/пороги/ключевые фразы зафиксированы в CONTRACTS §4.12; scene-выбор и sandbox-ограничения — KNOWLEDGE §4; миграции 0002 up/-1/up OK; паритет миграции↔модели зелёный.

## Stage 3 — REPORT (2026-09-20)
**Изменения**: транскрипция (faster-whisper, device fallback), scene detection (ffmpeg select), эвристический подбор кандидатов (6 фич, веса из env, NMS, top_k) + promote, миграция 0002 (transcript_segments, clip_candidates).
**Тесты**: `pytest -m "not real_services"` → **160 passed** (включая полный chain-тест upload→transcribe→candidates→promote→render→texts на моках); `RUN_REAL_INTEGRATION=1 pytest tests/integration` → **3 passed** (реальный ffmpeg: e2e render + scene cut). `scripts/verify_whisper.py` → SKIP (faster-whisper не установлен; HF egress заблокирован — модель не скачать).
**Блокеры**: реальная транскрипция на GPU — машина пользователя (`pip install -e ".[whisper]"`, `scripts/verify_whisper.py`; CUDA OOM→CPU покрыт моком).
**GATE: GO** — цепочка transcribe→scenes→candidates→promote→render→texts проходится (моки+синтетика+реальный ffmpeg для сцен/рендера), эвристики без обучения, pytest зелёный.

---

### T4.1–T4.3 — Dashboard — DONE (2026-09-20)
- Файлы: frontend/src/api.ts (типизированный fetch-клиент: videos/clips/jobs/renders/candidates/texts/publications/platform-accounts + ApiError с detail.code + fmt-хелперы), pages/VideosPage.tsx (upload form, список, детали: транскрибирование с poll, AI-кандидаты top-5, promote), pages/ClipsPage.tsx (фильтр по видео, manual create 5–180с, render с poll статуса через jobs, download presigned, тексты YT/TT), pages/PublishPage.tsx (форма аккаунта с Fernet-токеном (password input), форма ручной публикации, таблица публикаций со статусами/ошибками), AnalyticsPage (заглушка Stage 6). vite.config: host 0.0.0.0 + allowedHosts + dev-прокси /api→8000.
- Тесты: `npm run build` (tsc+vite) → OK; `npm run typecheck` → exit 0.
- **Живая проверка (dev-серверы в песочнице, цикл через UI-прокси :5173)**: upload настоящего mp4 → 201 ready; manual clip → draft; render → job succeeded, asset 1080x1920 h264 aac ready 331912 bytes (реальный ffmpeg); texts (fake LLM) → заголовок+хэштеги; platform account → created (credentials «***»); publish без реальных ключей → контролируемый 502 platform_error, Publication failed + last_error (без падения). Dashboard доступен пользователю как live preview.
- Статус: DONE.

### T4.4 — Аудит Stage 4 — DONE (2026-09-20)
- build/tsc зелёные; ручной чеклист (что видно): Videos — форма загрузки+таблица+детали с транскриптом/кандидатами; Clips — фильтр+создание+рендер+статусы+тексты+скачать; Publish — аккаунты+публикация+статусы; Analytics — заглушка Stage 6. Нет лендинга/маркетинговых элементов/лишних UI-либ (только react+router+tailwind). Backend регресс: **160 passed**.
- Статус: DONE.

## Stage 4 — REPORT (2026-09-20)
**Изменения**: функциональный dashboard (3 страницы + заглушка Analytics), типизированный api.ts, live-проверка полного цикла.
**Тесты**: npm build+typecheck OK; backend 160 passed; полный UI-цикл проверен на живых dev-серверах (uvicorn eager + moto S3 + vite) с реальным ffmpeg-рендером.
**Блокеры**: browser-взаимодействие проверено curl'ом через тот же прокси, что использует браузер; визуальный осмотр — за пользователем (live preview).
**GATE: GO**.

---

### T5.1 — Celery-перевод + Job lifecycle + reconcile — DONE (2026-09-20)
- Файлы: app/workers/job_lifecycle.py (mark_running/handle_success/handle_failure с retry-политикой: только идемпотентные, backoff 2^n×60; reconcile_stuck_jobs >15мин; requeue_retrying), app/workers/tasks.py (переписаны: _run_job-обёртка уважает сервисные failed-статусы; text_gen_task; publish_task без авто-ретраев; process_scheduled_publications), app/workers/celery_app.py (worker_ready → reconcile), app/infra/queue.py (beat 30с), app/api/v1/jobs.py (POST /jobs/reconcile), texts API → 202+Job.
- Тесты: unit lifecycle 7 (retry→retrying→failed по attempts, publish никогда, backoff 60/120/240, reconcile stuck→retrying/failed/fresh untouched, exhausted→failed) + полный suite регресс.
- Статус: DONE.

### T5.2 — Scheduling + autopublish + limits — DONE (2026-09-20)
- Файлы: publish_service.execute_scheduled_publication (атомарный claim scheduled→uploading rowcount-гард; external_post_id no-op guard), process_due_publications (due-выборка, дневные лимиты per-platform, min-interval, перенос scheduled_at без потерь).
- Тесты: 5 (due→published+external id; **двойной запуск → ровно 1 вызов upload + no-op при прямом re-execute**; daily limit 0 → rescheduled+status scheduled; min-interval → rescheduled (второй клип — partial unique блокирует тот же клип по дизайну); platform_error → failed+last_error). Полный suite: **172 passed**.
- Статус: DONE.

### T5.3 — Аудит Stage 5 — DONE (2026-09-20)
- CONTRACTS/ARCHITECTURE обновлены (202-контракт texts, reconcile endpoint, beat, лимиты, ADR-015). Живой Redis в песочнице отсутствует — Beat/reconcile проверены unit-уровнем + eager; ручная проверка на реальной машине: `celery -A app.workers.celery_app worker -B` (worker+beat) с живым Redis.

## Stage 5 — REPORT (2026-09-20)
**Изменения**: все длинные операции через Job (transcribe/render/text_gen уже, texts API → 202+Job), Job lifecycle с retry-политикой и reconcile на старте воркера, Celery Beat 30с, автопубликация due-scheduled с дневными лимитами/мин-интервалом/защитой от дублей (rowcount-гард + external_post_id), POST /jobs/reconcile.
**Тесты**: `pytest -m "not real_services"` → **172 passed** (включая доказательства: двойной запуск → 1 upload; лимит → перенос; publish не ретраится).
**Блокеры**: живой Redis+Beat — машина пользователя (команда в README); в песочнице eager-режим.
**GATE: GO** — ни одна длинная операция не блокирует HTTP синхронно (202+Job), reconcile работает (unit), автопубликация с защитой от дублей (mock-доказательство).

---

### T6.1 — Metrics sync via official API — DONE (2026-09-20)
- Файлы: app/models/metric.py (+миграция 0003, индекс (publication_id, captured_at)), app/services/analytics/metrics_service.py (MetricsAdapter Protocol; TikTokMetricsAdapter — Display API v2 /v2/video/query/ fields=view/like/comment/share_count, официальные доки в KNOWLEDGE §5), app/schemas/analytics.py, app/api/v1/analytics.py (POST sync-metrics 202+Job, GET metrics), workers.metrics_sync_task + sync_all_metrics, beat 15 мин.
- Тесты: адаптер против MockTransport (парсинг статистики, error-code, video_not_found) + flow с fake-адаптером (202→succeeded→Metric с raw+normalized, captured_at Z) + 409 not published + failed job. Миграции 0003 цикл OK.
- Статус: DONE.

### T6.2 — Analytics UI — DONE (2026-09-20)
- AnalyticsPage: таблица по опубликованным публикациям (views/likes/comments/shares, число синхронизаций), SVG-спарклайн динамики views (без chart-либ), кнопка «Синхронизировать метрики». npm build + typecheck OK.
- Статус: DONE.

### T6.3 — Аудит Stage 6 — DONE (2026-09-20)
- KNOWLEDGE §5: официальные источники TikTok-метрик с URL и датой (tiktok-api-v2-video-query, tiktok-api-v2-video-object). Никакого скрапинга. Полный suite: **178 passed**.

## Stage 6 — REPORT (2026-09-20)
**Изменения**: метрики через официальный TikTok Display API (video/query), Job metrics_sync + beat 15 мин, хранение raw+normalized, endpoints sync-metrics/metrics, AnalyticsPage с динамикой.
**Тесты**: `pytest -m "not real_services"` → **178 passed**; frontend build+typecheck OK.
**Блокеры**: реальные метрики — нужны ключи на машине пользователя (dry-путь покрыт fake-адаптером и MockTransport).
**GATE: GO** — метрики только официальным путём (доказано адаптером по официальным докам), raw+normalized хранятся, отображаются в dashboard.

---

### T7.1 — Датасет самообучения — DONE (2026-09-20)
- `dataset_service.build_training_dataset`: Publication(published, external_post_id) → clip.features (копия фич кандидата при promote) → ПОСЛЕДНИЙ Metric → LabeledRow (7 фич + duration_sec из window; target log1p(views), fallback взвешенный engagement; строки без фич/метрик — skipped с причинами). Никаких синтетических меток.
- Статус: DONE.

### T7.2 — Обучение + eval-гейт — DONE (2026-09-20)
- `ml_ranker.train_and_evaluate`: lightgbm (fallback sklearn GBRT), time-ordered split (новейшие ml_val_fraction — валидация), Spearman на val против ТОЧНОЙ реплики эвристической формулы; гейт = ml>baseline И ml>0. Прошёл → joblib в `models/` (вне git) + TrainingRun(succeeded); нет → TrainingRun(rejected), модель не активируется. Pyproject: extra `[ml]` (scikit-learn, lightgbm, joblib) — ARCHITECTURE ADR-016. Модель старше ml_max_age_days не активна.
- Тесты: spearman sanity (ties/инверсия/константа), gate pass (сигнал в duration, эвристикой игнорируется) → модель активна + rerank переупорядочивает, gate fail (константный таргет) → rejected + heuristic fallback, ml_rerank_enabled=false → None.
- Статус: DONE.

### T7.3 — Rerank + self-training + UI — DONE (2026-09-20)
- `candidate_service.generate_candidates` → (rows, ranked_by); rerank с fallback при любой ошибке; features.ml_score. API: POST /ml/train (202+Job ml_train, миграции 0005 ref_id NULL + 0006 ck type), GET /ml/runs, GET /ml/dataset-status. Beat `self_train_check` 6ч (≥ ml_retrain_min_new_rows новых строк). UI: бейдж ML-rerank/эвристика в VideosPage, секция ML в AnalyticsPage (датасет, обучение, история прогонов, результат гейта).
- Тесты: API train→succeeded→runs; self_train_check на пустой БД → retrained:false. Полный suite: **186 passed**; frontend build+typecheck OK.
- Статус: DONE.

## Stage 7 — REPORT (2026-09-20)
**Изменения**: датасет «фичи клипа → метрики публикации», GBM-ранкер с eval-гейтом (активация только при превышении эвристики), rerank кандидатов с автоматическим fallback, self-training beat, панель ML в UI.
**Тесты**: `pytest -m "not real_services"` → **186 passed**; миграции 0003–0006 цикл OK; npm build+typecheck OK.
**Блокеры**: реальное обучение имеет смысл при накоплении публикаций (ml_min_training_rows=30); в песочнице проверено синтетикой + гейт-механикой, честно задокументировано.
**GATE: GO** — UC-6 закрыт (эвристики → ML с fallback, доказано тестами), §3.6 реализована отдельным этапом после MVP, как требовал спек.

---

# ФИНАЛЬНЫЙ ОТЧЁТ ПО ПРОЕКТУ (§9 DoD) — 2026-09-20

- **UC-1..UC-9** (MASTER_SPEC §3): все покрыты тестами/живой проверкой в песочнице (UC-1..5,7,8 — Stage 4 live e2e через UI; UC-6 — Stage 7 тесты rerank+fallback; UC-9 метрики — Stage 6, live блокируется только egress песочницы, путь официальный).
- **docs/KNOWLEDGE.md**: проверенные URL официальных доков TikTok (публикация + метрики) с датами (2026-09-20) — да.
- **README quickstart**: запуск с нуля несколькими командами (venv → deps → сервисы → alembic → uvicorn/worker/beat+vite) — да, включая честные пометки о песочнице.
- **Stage gates**: Stage 0–7 все GATE: GO с отчётами §30 в этом файле.
- **Коммиты по стадиям**: c37ab3e (S1) → 3513e2d (S2) → 944184b (S3) → d04bdfe (S4) → 24e32f3 (S5) → 0b49fd8 (S6) → настоящий (S7).
- **Честные ограничения**: faster-whisper (нет egress до HF) — SKIP с mocked-проверкой и инструкцией; реальные платформенные ключи — controlled-fail пути проверены; Redis/Postgres/MinIO в песочнице — sqlite+moto+eager, на реальной машине через env.
