# CONTRACTS — доменные сущности, БД, API

> Приоритет: MASTER_SPEC > **CONTRACTS** > ARCHITECTURE > AGENTS > KNOWLEDGE > PROGRESS.
> Contract-first: любое изменение поведения/схемы/API — сначала здесь, затем код в том же тикете.

## 1. Общие конвенции

- Python: файлы/функции/переменные — `snake_case`. Таблицы БД — `snake_case` **множественное число** (`videos`, `clips`, ...).
- PK — UUIDv4 (Python `uuid4`, тип `sa.Uuid()` → PG `UUID`, SQLite `CHAR(32)`).
- Timestamps — `timestamptz` (`DateTime(timezone=True)`), UTC, `created_at` default now, `updated_at` onupdate now. В API — ISO8601 UTC **с Z** (`2026-09-20T12:00:00Z`).
- **Статусы: `varchar` + `CHECK`** (не native PG enum) — единый стиль на всех СУБД (ADR-003). В коде — классы строковых констант; в Pydantic — `Literal`.
- JSONB: `sa.JSON().with_variant(postgresql.JSONB(), "postgresql")` (PG=JSONB, SQLite=JSON) — одинаково в моделях и миграциях.
- Миграции: только Alembic, отдельная ревизия на изменение, upgrade/downgrade обязаны работать (тест `test_migrations.py` сравнивает схему из миграций со схемой из метаданных моделей).
- `create_all` запрещён в прод-коде (только тест сравнения схем).
- Пагинация: `limit` (default 20, max 100) + `offset` (default 0).
- Единый формат ошибок:
  ```json
  {"detail": {"code": "snake_case_code", "message": "human readable", "fields": {"field": "why"}}
  ```
  `fields` — `null` или словарь. Ошибка валидации FastAPI → 422 `{"code": "validation_error", "fields": {...}}`.

## 2. Сущности (Stage 0–1)

### 2.1 Video — `videos`
| Поле | Тип | Правила |
|---|---|---|
| id | UUID PK | uuid4 |
| original_filename | varchar(255) | как прислал пользователь |
| storage_key | varchar(512) **unique** | `videos/{video_uuid}/{safe_name}` |
| size_bytes | bigint | >0 |
| mime_type | varchar(64) | allowlist: video/mp4, video/quicktime, video/webm, video/x-matroska |
| duration_sec | float null | из ffprobe (опционально; null если ffprobe недоступен/ошибка) |
| width, height | int null | из ffprobe |
| status | varchar(16) + CHECK | `uploading | ready | failed | deleted` |
| error_message | text null | |
| created_at / updated_at | timestamptz | |

Индекс: `ix_videos_status`.
**Жизненный цикл:** `uploading` (строка создаётся при приёме файла) → `ready` (S3 upload + опц. ffprobe) | `failed` (storage_error). Удаление Video — soft (`deleted`); FK `RESTRICT` защищает от физического удаления при существующих clips (ADR FK).

### 2.2 Clip — `clips`
| Поле | Тип | Правила |
|---|---|---|
| id | UUID PK | |
| video_id | UUID FK→videos.id, ondelete RESTRICT | indexed |
| title | varchar(140) | 1..140 |
| start_sec, end_sec | float | CHECK `start_sec >= 0`, CHECK `end_sec > start_sec` |
| status | varchar(16) + CHECK | `draft | render_queued | rendering | rendered | render_failed` |
| score | float null | Stage 3+ |
| features | JSONB null | Stage 3+ |
| created_at / updated_at | timestamptz | |

Индекс: `ix_clips_video_id_status (video_id, status)`.
Валидация длительности (уровень сервиса, конфиг `CLIP_MIN_SEC=5`, `CLIP_MAX_SEC=180`): `clip_too_short` / `clip_too_long`; `end_sec <= video.duration_sec` — только если duration известна (ffprobe НЕ вызывается в этом flow).

### 2.3 Job — `jobs`
| Поле | Тип | Правила |
|---|---|---|
| id | UUID PK | |
| type | varchar(16) + CHECK (attr `job_type`, колонка `type`) | `transcribe | render | text_gen | publish | metrics_sync | train` |
| ref_type | varchar(16) | `video | clip | publication | candidate` (полиморфная ссылка, без FK) |
| ref_id | UUID | |
| status | varchar(12) + CHECK | `queued | running | succeeded | failed | retrying | cancelled` |
| attempts, max_attempts | int | default 0 / 3 |
| idempotency_key | varchar(255) **unique null** | |
| payload / result | JSONB null | |
| error_message | text null | без секретов, stderr-хвост ≤2KB |
| scheduled_at / started_at / finished_at | timestamptz null | |
| created_at / updated_at | timestamptz | |

Индексы: `ix_jobs_status_type (status, type)`, `ix_jobs_ref (ref_type, ref_id)`.

### 2.4 RenderedAsset — `rendered_assets`
| Поле | Тип | Правила |
|---|---|---|
| id | UUID PK | |
| clip_id | UUID FK→clips.id, ondelete **CASCADE** | indexed |
| storage_key | varchar(512) unique | `renders/{clip_id}/{asset_id}.mp4` |
| size_bytes | bigint | |
| width / height | int | 1080 / 1920 |
| codec_video / codec_audio / pix_fmt | varchar(16) | `h264` / `aac` / `yuv420p` |
| duration_sec | float | end−start |
| status | varchar(12) + CHECK | `rendering | ready | failed` |
| created_at | timestamptz | |

### 2.5 PlatformAccount — `platform_accounts`
| Поле | Тип | Правила |
|---|---|---|
| id | UUID PK | |
| platform | varchar(16) + CHECK | `youtube | tiktok` |
| external_account_id | varchar(255) | **unique (platform, external_account_id)** |
| display_name | varchar(255) null | |
| credentials_encrypted | text | Fernet; **никогда** в логах/API (в ответах — `***`) |
| scopes | JSONB | список scope строк |
| expires_at | timestamptz null | |
| is_active | bool | |
| created_at / updated_at | timestamptz | |

### 2.6 Publication — `publications`
| Поле | Тип | Правила |
|---|---|---|
| id | UUID PK | |
| clip_id | UUID FK→clips.id, ondelete RESTRICT | |
| rendered_asset_id | UUID FK→rendered_assets.id null, ondelete SET NULL | |
| platform_account_id | UUID FK→platform_accounts.id, ondelete RESTRICT | |
| platform | varchar(16) + CHECK | `youtube | tiktok` |
| external_post_id | varchar(255) null | ID поста на платформе |
| status | varchar(16) + CHECK | `draft | scheduled | uploading | published | failed | cancelled` |
| scheduled_at, published_at | timestamptz null | |
| idempotency_key | varchar(255) **unique** | `{clip_id}:{platform}:{asset_id}:{sha256(title)[:12]}` (фиксация Stage 1.4) |
| attempt_count | int | |
| last_error | text null | без секретов |
| metadata | JSONB null (attr `meta`, колонка `metadata`) | title/desc/tags/privacy |
| created_at / updated_at | timestamptz | |

Индексы: `ix_publications_clip_platform_status (clip_id, platform, status)`;
**Partial unique**: `uq_publications_active` — UNIQUE `(clip_id, platform)` WHERE `status NOT IN ('cancelled','failed')` (одна «активная» публикация на клип+платформу).

### 2.7 Будущие сущности (фиксация вперёд)
- **TranscriptSegment** (Stage 3): `transcript_segments(id, video_id FK, start, end, text, avg_confidence, words JSONB)`.
- **ClipCandidate** (Stage 3): `clip_candidates(id, video_id FK, start, end, score, features JSONB, reason)`.
- **Metric** (Stage 6): `metrics(id, publication_id FK, captured_at, views, likes, comments, shares, raw JSONB)`, индекс `(publication_id, captured_at)`.
- **MlModel** (Stage 7): `ml_models(version unique, storage_key, metrics JSONB, trained_at, is_active, fallback_reason)`; активна ровно одна.

## 3. FK / delete-политика (ADR-FK)

| FK | Поведение | Обоснование |
|---|---|---|
| clips.video_id → videos | RESTRICT | удаление Video — soft (`status=deleted`); физическое удаление запрещено при клипах; покрыто тестом |
| rendered_assets.clip_id → clips | CASCADE | артефакты рендера не имеют смысла без клипа |
| publications.clip_id → clips | RESTRICT | публикации — бизнес-записи, не терять |
| publications.rendered_asset_id | SET NULL | публикация переживает удаление ассета |
| publications.platform_account_id | RESTRICT | история публикаций не отвязывается от аккаунта |

## 4. API v1 (Stage 0–1 реализовано; расширения — аддитивно)

Базовый префикс `/api/v1`. Даты — ISO8601 UTC c `Z`.

### 4.1 GET /health → 200
```json
{"status": "ok", "version": "0.1.0", "checks": {"db": "ok", "redis": "skip", "s3": "ok"}}
```
`checks.*` ∈ `ok | skip` (skip = сервис недоступен/не настроен; liveness всегда 200).

### 4.2 POST /api/v1/videos — загрузка (multipart/form-data, поле `file`)
- Лимит `UPLOAD_MAX_MB` (default 1024); allowlist mime `video/mp4|video/quicktime|video/webm|video/x-matroska` + расширение `.mp4|.mov|.webm|.mkv`; потоковая запись чанками 1MB во временный файл (не в RAM), затем stream-upload в S3.
- Content-Length > лимит (+2MB slack на multipart) → 413 **до** полной записи.
- Ключ: `videos/{uuid}/{safe_name}`; safe_name: lower, `[a-z0-9._-]`, ≤80 симв (санитизация).
- ffprobe для Video **разрешён** на этом шаге (запрет касается только manual-clip валидации); при недоступности/ошибке — `duration_sec: null`, статус `ready`.
- Ответ **201** `VideoRead`:
```json
{"id": "…uuid…", "original_filename": "video.mp4", "storage_key": "videos/…/video.mp4",
 "size_bytes": 1048576, "mime_type": "video/mp4", "duration_sec": 12.5, "width": 1280,
 "height": 720, "status": "ready", "error_message": null,
 "created_at": "2026-09-20T10:00:00Z", "updated_at": "2026-09-20T10:00:00Z"}
```
- Ошибки: `400 empty_file`, `413 payload_too_large`, `415 unsupported_media`, `500 storage_error`.

### 4.3 GET /api/v1/videos?limit=&offset= → 200
```json
{"items": [VideoRead, ...], "total": 42}
```

### 4.4 GET /api/v1/videos/{video_id} → 200 VideoRead / 404 `video_not_found` / 422 (невалидный UUID)

### 4.5 POST /api/v1/videos/{video_id}/clips/manual
```json
{"title": "Best moment", "start_sec": 12.5, "end_sec": 42.0}
```
→ **201** `ClipRead` (status `draft`). Ошибки: `400 invalid_range | clip_too_short | clip_too_long`, `404 video_not_found`, `409 video_not_ready`. ffprobe в этом flow **не вызывается** (проверено grep + mock-тестом).
```json
{"id": "…", "video_id": "…", "title": "Best moment", "start_sec": 12.5, "end_sec": 42.0,
 "status": "draft", "score": null, "features": null,
 "created_at": "2026-09-20T10:01:00Z", "updated_at": "2026-09-20T10:01:00Z"}
```

### 4.6 GET /api/v1/clips?video_id=… → 200 `{"items": [ClipRead]}`; GET /api/v1/clips/{clip_id} → 200 / 404 `clip_not_found`

### 4.7 POST /api/v1/clips/{clip_id}/render → 202
```json
{"job_id": "…uuid…", "clip_id": "…uuid…", "status": "render_queued"}
```
- Clip: `draft|render_failed` → постановка в Job(type=render); `render_queued|rendering` → **409 already_rendering**; `rendered` → **идемпотентный ответ 202** с существующим succeeded job (`status: "rendered"`); `rendered` без готового asset → 422 `invalid_clip_state`; video не ready → 422 `invalid_clip_state`.
- Повторный render после `render_failed` разрешён (новый job с ключом `render:{clip_id}:{n}`).
- Статус опрашивается `GET /api/v1/jobs/{job_id}`; результат в `result.asset_id`.

### 4.8 GET /api/v1/renders/{asset_id} → 200 RenderedAssetRead / 404 `asset_not_found`
### 4.9 GET /api/v1/renders/{asset_id}/download → 200
```json
{"url": "https://…presigned…", "expires_sec": 900}
```
(S3 — presigned URL; фиксация. Локальный file-режим не предусмотрен.)

### 4.10 GET /api/v1/jobs/{job_id} → 200 JobRead / 404 `job_not_found`
```json
{"id": "…", "type": "render", "status": "succeeded", "ref_type": "clip", "ref_id": "…",
 "attempts": 1, "max_attempts": 3, "idempotency_key": "render:…", "payload": {…},
 "result": {"asset_id": "…"}, "error_message": null,
 "scheduled_at": null, "started_at": "…", "finished_at": "…",
 "created_at": "…", "updated_at": "…"}
```

### 4.11 Публикации (реализовано в Stage 1.4; первая платформа — TikTok, выбор пользователя 2026-09-20)
- `POST /api/v1/publications/manual` body:
```json
{"clip_id": "…", "platform": "tiktok", "platform_account_id": "…", "title": "…",
 "description": "…", "privacy": "public", "scheduled_at": null}
```
→ 201 PublicationRead (status `published` при успешной немедленной загрузке | `scheduled` при `scheduled_at` — публикация отложена до Stage 5 worker). Ошибки: `404 clip_not_found | asset_not_found | account_not_found`, `409 duplicate_publication`, `422 validation_error` (platform mismatch/privacy), `502 platform_error` (Publication → failed + last_error без секретов).
- `GET /api/v1/publications?clip_id=&platform=`, `GET /api/v1/publications/{id}` → 200/404 (`publication_not_found`).
- **Идемпотентность (фиксация)**: `idempotency_key = {clip_id}:{platform}:{asset_id}:{sha256(title)[:12]}`; повторный POST с тем же ключом → 409 `duplicate_publication`. Retry после `failed` — новый ключ (другой title) разрешён; `failed`/`cancelled` не блокируют (partial unique).
- **Privacy-маппинг (TikTok)**: `public→PUBLIC_TO_EVERYONE`, `unlisted→MUTUAL_FOLLOW_FRIENDS` (у TikTok нет unlisted), `private→SELF_ONLY`. Значение обязано входить в `privacy_level_options` creator'а (иначе платформа отклонит).
- **Credentials**: `PlatformAccount.credentials_encrypted` = Fernet(JSON `{"access_token": "...", ...}`). В API — всегда `"***"`. Управление аккаунтами:
  - `POST /api/v1/platform-accounts` body `{"platform", "external_account_id", "display_name"?, "credentials": {...}, "scopes"?}` → 201 (credentials=`"***"`).
  - `GET /api/v1/platform-accounts` → `{"items": [...], "total": N}`.
- **TikTok адаптер** (только по официальным докам, см. KNOWLEDGE §2 с URL и датами): Direct Post `POST /v2/post/publish/video/init/` (scope `video.publish`, FILE_UPLOAD) → `PUT {upload_url}` (Content-Range) → `POST /v2/post/publish/status/fetch/` до `PUBLISH_COMPLETE|FAILED`; title ≤2200 симв; unaudited app → посты только приватные (платформа вернёт 403 `unaudited_client_can_only_post_to_private_accounts`).
- `metadata` в ответе — Publication.meta (title/description/privacy).

### 4.12 Будущие эндпоинты (фиксация)
- Stage 2 (реализовано): `POST /api/v1/texts/generate` body `{"clip_id", "platform": "youtube|tiktok", "tone"?, "transcript"?}` → 200 `{"job_id": null, "texts": {"titles": [3], "description", "hashtags"}, "captions_srt", "platform"}` (Stage 2 синхронно, job_id=null; Stage 5 — через Job, контракт сохраняет оба поля). Ошибки: 404 `clip_not_found`, 422 (platform), 502 `text_gen_error` (провайдер недоступен/invalid JSON после 1 ретрая; создаётся Job text_gen failed с error_message).
  - `GET /api/v1/clips/{id}/texts?platform=` → 200 `{clip_id, platform, texts|null}` — тексты читаются из последнего succeeded Job(type=text_gen).result (хранение без отдельной таблицы; единый контракт для sync/async).
  - Провайдеры: `LLM_BACKEND=fake` (детерминированный, default) | `ollama` (реальный локальный, /api/chat format=json, OOM→retry num_gpu=0 = CPU fallback, фиксируется device_used) | `llamacpp`/`transformers` (честные not_implemented).
  - Лимиты: YouTube title ≤100, description ≤5000, tags total ≤500; TikTok title/caption ≤2200 (официальный лимит, KNOWLEDGE §2), hashtags 3–8 с авто-«#».
- Stage 3 (реализовано):
  - `POST /api/v1/videos/{id}/transcribe` → 202 `{job_id, video_id, status:"queued"}` (Job type=transcribe, идемпотентен по ключу `transcribe:{video_id}`; повторный вызов → тот же job, result.cached=true). Ошибки: 404 `video_not_found`, 409 `video_not_ready`. В `result`: `segment_count, device_used, compute_type, model, language`. `GET /api/v1/videos/{id}/transcript` → `{items: [TranscriptSegmentRead], total}` (404 если видео нет).
  - `POST /api/v1/videos/{id}/candidates?top_k=5` (default 5, 1..20) → 200 `CandidatePage` (строки clip_candidates: start/end/score/features/reason). Требует транскрипт (иначе 409 `transcript_missing`) и известную duration (иначе пробует ffprobe, при неудаче 422 `video_metadata_missing`); 409 `video_not_ready`. Регенерация заменяет прежних кандидатов видео. `GET /api/v1/videos/{id}/candidates` → сохранённые, по убыванию score.
  - `POST /api/v1/candidates/{id}/promote` body `{"title"?}` → 201 `ClipRead` (status=draft, score/features наследуются; title по умолчанию — текст первого сегмента ≤60 симв). 404 `candidate_not_found`, 422 `invalid_clip_state` (окно вне лимитов).
  - Эвристики (§18): скользящие окна 15/30/45/60с шаг 5с; фичи speech_ratio / key_phrases (список RU+EN маркеров в `features.py`) / tempo_wpm (bell-оптимум 120–180) / loudness (RMS из 16k mono wav через stdlib audioop, нормировка /20000) / position (интро <30с бонус=1.0, финал −5с=0.3, иначе 0.5) / scene_alignment (границы ±2с). Итог = взвешенная сумма с весами AI_WEIGHTS_* (default 0.3/0.25/0.15/0.15/0.15). NMS IoU>0.5, top_k. Детекция сцен: ffmpeg `select='gt(scene,0.4)'` + showinfo (ADR; без PySceneDetect/OpenCV); fallback — равномерные окна 30с. Границы сцен хранятся в features каждого кандидата (scene_boundaries, scene_fallback) и не кэшируются отдельно.
- Stage 6 (реализовано):
  - `POST /api/v1/publications/{id}/sync-metrics` → **202** `{job_id, publication_id, status}` — Job metrics_sync; адаптеры только официальные (TikTok Display API `POST /v2/video/query/`).
  - `GET /api/v1/publications/{id}/metrics` → `{items: Metric[], total}` — снимки во времени (raw+normalized), `captured_at` ASC.
  - Beat: `sync_all_metrics` каждые 15 мин — Job'ы на все published с external_post_id.
- Stage 7 (реализовано):
  - `POST /api/v1/ml/train` → **202** `{job_id, status}` — обучение ML-rerank с eval-гейтом (job ml_train, ref_type=system, ref_id=NULL).
  - `GET /api/v1/ml/runs?limit=` → `{items: TrainingRun[], total}` — история обучений (val_spearman, baseline_spearman, gate_passed, model_version).
  - `GET /api/v1/ml/dataset-status` → `{rows, skipped, targets}` — размер обучающего датасета.
  - `POST /api/v1/videos/{id}/candidates` → `{items, total, ranked_by}` — `ranked_by: "ml"|"heuristic"`; при активной модели кандидаты переупорядочены по ML-score (features.ml_score), иначе эвристика.
  - Eval-гейт (§23): модель активируется ТОЛЬКО если val Spearman(ML) > Spearman(эвристики на тех же строках) и > 0; иначе run=rejected, работает эвристика. Модель старше ml_max_age_days → не активна. Никаких синтетических меток: датасет = published клипы (фичи promote) + последний Metric.
  - Beat: `self_train_check` каждые 6 ч — дообучение при ≥ ml_retrain_min_new_rows новых строк с прошлого прогона.
- Stage 10 / Dashboard 2.0 (реализовано):
  - `GET /api/v1/jobs?status=&type=&limit=&offset=` → `{items: JobRead[], total}` — список Job (новые сверху) с фильтрами; для очереди и баннера сбоев.
  - `GET /api/v1/overview` → `{videos: {status: n}, clips: {...}, jobs: {...}, publications: {...}, scheduled_next_at, failed_jobs_recent, latest_metrics: {publications, views, likes, comments, shares}, ml: {dataset_rows, active_model}}` — агрегат для главной; ОДИН вызов вместо клиентского N+1.
  - `GET /api/v1/clips/{clip_id}/asset` → 200 RenderedAssetRead | 404 `asset_not_found` — последний READY-ассет клипа (превью/скачивание переживают перезагрузку страницы).
  - `PATCH /api/v1/clips/{clip_id}` → 200 ClipRead | 400 `invalid_range`/`invalid_clip_state` | 409 `clip_not_editable` — правка title/start/end ТОЛЬКО в статусе draft; длительность в пределах clip_min/max.
  - `GET /api/v1/ml/active-model` → `{active: bool, model_version?, backend?, feature_keys?}` — индикатор активной ML-модели (false → эвристика).
- Stage 8 / YouTube (реализовано, вторая платформа по решению пользователя):
  - Платформа `youtube` во всех platform-полях (Literal + ck constraint были заложены со Stage 0). Реестр publisher'ов перенесён в `publish/base.py` (`register_publisher`/`get_publisher`, ленивая загрузка адаптеров) — ядро publish_service не изменилось (§15).
  - `YouTubePublisher`: официальный resumable-протокол videos.insert (init → Location → PUT байты); privacy 1:1 (public/unlisted/private — нативно); title≤100, description≤5000, tags≤500 символов; `resolve_access_token` — access_token или OAuth2 refresh (client_id/secret из credentials или настроек youtube_*).
  - Метрики: `YouTubeMetricsAdapter` — videos.list part=statistics (views/likes/comments; shares=None — API не отдаёт).
  - Ошибки: PlatformError с кодами missing_credentials/token_refresh_failed/upload_init_failed/upload_failed/video_not_found; в сообщениях только reason+message из Google error body (без секретов).
- Stage 5 (реализовано):
  - `POST /api/v1/texts/generate` → **202** `{job_id, texts (могут быть пустыми до завершения job), captions_srt, platform}` — генерация исполняется Job'ом; результат — `GET /clips/{id}/texts`.
  - `POST /api/v1/jobs/reconcile` → `{reconciled: {retrying, failed}, requeued}` — ручной запуск восстановления застрявших Job (автоматически — при старте воркера, сигнал worker_ready: running/queued без прогресса > 15 мин → retrying (идемпотентные) / failed).
  - Retry-политика: ретраятся ТОЛЬКО идемпотентные типы (transcribe/render/text_gen/metrics_sync) с экспоненциальным backoff 2^attempt×60с; publish НИКОГДА не ретраится автоматически (дубли защищены idempotency_key + external_post_id + атомарным переходом scheduled→uploading).
  - Beat: `process_scheduled_publications` каждые 30с — публикация due scheduled (scheduled_at<=now). Rate limits: {TIKTOK|YOUTUBE}_DAILY_LIMIT (дневной счётчик по published за UTC-день) и PUBLISH_MIN_INTERVAL_SEC (интервал между публикациями платформы); при лимите — перенос scheduled_at вперёд (без потерь, без дублей). ADR-015: вместо Redis SET NX (нет Redis в dev) — атомарный UPDATE ... WHERE status='scheduled' (rowcount-гард) + проверка external_post_id перед повторной отправкой; Redis-lock добавляется поверх при необходимости в проде.
- Stage 6: `POST /api/v1/publications/{id}/sync-metrics` → 202; `GET /api/v1/publications/{id}/metrics`.
- Stage 7: `POST /api/v1/ml/train` → 202; `GET /api/v1/ml/models`; `POST /api/v1/ml/models/{v}/activate`; `GET /api/v1/ml/dataset/stats`.

## 5. Render spec (Stage 1.3, канон)

- Выход: MP4, `-c:v libx264 -preset veryfast -crf 23`, `-c:a aac -b:a 128k`, 1080x1920, `-pix_fmt yuv420p`, `-movflags +faststart`, `-r 30` (фиксация: форс 30 fps).
- Фильтр: `scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,setsar=1` (center-crop).
- Порядок аргументов: быстрый seek `-ss {start}` **до** `-i`, точная обрезка `-t {duration}` после `-i` (фиксация).
- Только `services/render/ffmpeg_runner.py` запускает subprocess: list-args, `shell=False`, `timeout=FFMPEG_TIMEOUT_SEC`, stderr-хвост ≤2KB в лог/Job (не в API полностью).
- Controlled errors: `ffmpeg_missing`, `render_timeout`, `render_failed`, `invalid_timestamps` → Job failed + Clip `render_failed`, API не падает.

---

# ЧАСТЬ CR — Content Rewards (creator monetization), Stage CR-0..CR-9 — v2 (правки по ревью 2026-09-22)

> Зафиксировано 2026-09-22 по директиве пользователя; **v2 — после репозиторной ревь**ю: versioned terms вынесены в неизменяемую таблицу, добавлен audit-log переходов, закреплён денежный контракт, уточнены факты fee/scopes. **Код CR-1+ не начинается до согласования этой версии контракта** (гейт CR-0). Продукт: creator-only, Whop-first, provider-neutral, USD-first (ISO currency ready). Главные KPI: фактическая чистая подтверждённая выплата; ожидаемая чистая выплата за клип; выплата за час активной работы; approval rate; доля отправленных вовремя ссылок; доля клипов без нарушений brief. Просмотры — промежуточный сигнал.

## CR-0.1 Сущности и миграции — 11 таблиц, 4 миграции (0007–0010)

Правила: деньги — см. CR-0.4; модель == миграция (parity-тест, как 0001–0006); FK-политики как в §2.

### 0007 — кампании (4 таблицы)
**`reward_campaigns`**: `id` PK; `provider` str16 (`whop_content_rewards`); `external_campaign_id` str128; **uq (provider, external_campaign_id)**; `name` str255; `brand_name` str255 null; `source_url` str1024 (обязателен при импорте); `status` str16 (`draft|active|paused|closed|unknown`); `payout_model` str16 (`cpm|per_post|retainer`); `platforms` json ⊆ `tiktok|youtube|instagram|x`; `currency` char3 ISO-4217 default `USD`; `budget_total`/`budget_spent` NUMERIC(14,2) null (снимок, не realtime); `cpm_rate` NUMERIC(10,4) null; `per_post_amount` NUMERIC(12,2) null; `retainer_amount` NUMERIC(12,2) null; `retainer_cycle_days` int null; `min_payout`/`max_payout_per_clip` NUMERIC(12,2) null; `deadline_at` timestamptz null; `current_terms_version_id` FK→campaign_terms_versions null (ставится при подтверждении термов пользователем); `active_brief_version_id` FK→campaign_brief_versions null (только действием пользователя); `imported_payload` json; timestamps. **Термы НЕ хранятся полями кампании** (см. campaign_terms_versions).

**`campaign_terms_versions`** — НЕИЗМЕНЯЕМЫЕ versioned campaign terms (ревью: «нельзя просто изменять в reward_campaigns»): `id` PK; `campaign_id` FK CASCADE; `version` int ≥1 **uq (campaign_id, version)**; `content_hash` char64 (sha256 канонического JSON термов — контроль неизменности); `creator_fee_percent` NUMERIC(5,2); `fee_free_budget_threshold` NUMERIC(12,2) (per-post/retainer с бюджетом ≥ порога → 0%; дефолт 5000 по KNOWLEDGE §7, но подтверждается при импорте); `earnings_window_days` int; `payout_hold_days` int; `submission_deadline_minutes` int; `terms_source_url` str1024; `terms_checked_at` timestamptz; `confirmed_at` timestamptz null (подтверждение пользователем); `created_at`. Строки только INSERT; изменение термов = новая версия; снапшоты/сабмишены ссылаются на конкретную версию.

**`campaign_brief_versions`**: `id` PK; `campaign_id` FK; `version` int **uq (campaign_id, version)**; `status` (`pending_approval|approved|rejected|superseded`) — автактивации нет; источник: `raw_text` text null | `raw_file_key` str512 null | `structured_json`; `source_url` str1024; `checklist` json (CR-2: `{requirement_id, category, rule, expected, severity_hint, confidence, source_span, extracted_value}`); `parser_engine` str32; `parser_confidence` NUMERIC(4,3); `supersedes_id` FK self null; `approved_at` null; `created_at`. Новая approved версия → ранее проверенные клипы stale (re-run compliance).

**`campaign_source_assets`**: `id` PK; `campaign_id` FK; `brief_version_id` FK; `kind` (`video|audio|image|link`); `storage_key` str512 null | `external_url` str1024 null; `sha256` char64 null; `title` str255; `authorized` bool default **false** (явная авторизация пользователя); `authorization_note` text null; `created_at`.

### 0008 — клипы кампаний и комплаенс (3 таблицы)
**`campaign_clips`**: `id` PK; `campaign_id` FK; `clip_id` FK RESTRICT **uq**; `brief_version_id` FK; `render_asset_id` FK SET NULL; `render_sha256` char64 (фиксируется при публикации; подмена файла — blocker); `variant_label` str64 null; `created_at`. **Осознанное продуктовое ограничение (зафиксировано по ревью)**: один Clip принадлежит максимум одной кампании — переиспользование одного рендера в нескольких кампаниях = риск rejection «reused content» (типовая причина отказов, KNOWLEDGE §7) и дубликата публикации на платформе. Для другой кампании создаётся новый Clip/вариант.

**`compliance_check_runs`**: `id` PK; `campaign_clip_id` FK; `brief_version_id` FK; `status` (`passed|failed|warnings|error`); `counts` json `{blocker,warning,manual_review}`; `started_at/finished_at`; `created_at`.
**`compliance_findings`**: `id` PK; `check_run_id` FK CASCADE; `rule_code` str64 (CR-3.2); `severity` (`blocker|warning|manual_review`); `passed` bool; `message` text; `details` json; `created_at`.

### 0009 — сабмишены (3 таблицы)
**`reward_submissions`**: `id` PK; `campaign_clip_id` FK; `campaign_id` FK; `terms_version_id` FK **NOT NULL** (термы, действовавшие на момент сабмишена); `provider` str32; `status` (CR-0.3); `idempotency_key` str255 **uq**; `post_url` str1024; `posted_at` timestamptz; `posted_render_sha256` char64; `submission_deadline_at` = posted_at + terms.submission_deadline_minutes; `submitted_at` null; `submitted_via` (`manual|api`); `external_submission_id` str255 null; `rejection_reason` text null; деньги (CR-0.4): `payout_gross_expected`/`payout_net_expected` NUMERIC(12,2) (forecast на решение «постить»), `payout_gross_actual`/`fee_amount_actual`/`payout_net_actual` NUMERIC(12,2) null; `currency` char3; `paid_at` null; `last_error` text null; timestamps. Индексы: (campaign_id, status), (status, submission_deadline_at).

**`reward_submission_events`** — audit-log переходов (ревью: «отдельные evidence/timestamps»): `id` PK; `submission_id` FK CASCADE; `from_status`/`to_status` str16; `decision` str32; `actor` (`user|system|provider`); `evidence` json (обязателен для user-решений: сниппет rejection note, URL, скрин-ссылка и т.п.); `idempotency_key` str255 **uq**; `created_at`.

**`reward_snapshots`**: `id` PK; `submission_id` FK CASCADE; `captured_at` timestamptz; `views` bigint null; `views_kind` (`platform_official|provider_reported|user_reported`); `payout_gross_cumulative`/`payout_net_cumulative` NUMERIC(12,2) null; `raw` json. Индекс (submission_id, captured_at).

### 0010 — производственные сессии (1 таблица)
**`production_sessions`**: `id` PK; `campaign_id` FK null; `started_at`; `ended_at` null; `active_minutes` int; `clips_produced` int; `notes` text null; `created_at`. Основа KPI «выплата за час активной работы».

## CR-0.4 Денежный контракт
- **Валюта**: `currency` char3 ISO-4217; одна валюта на кампанию; кросс-валютная арифметика запрещена (конвертация — вне скоупа).
- **Precision**: суммы `NUMERIC(14,2)`; ставки CPM `NUMERIC(10,4)`; проценты `NUMERIC(5,2)`. В Python — только `Decimal`; `float` для денег запрещён (audit-правило).
- **Rounding**: промежуточные вычисления — полная точность Decimal; квантование до сотых **ROUND_HALF_EVEN** только на границах записи (expected/actual payout, fee). Модель==миграция по scale.
- **Gross / creator fee / net** (раздельно, по ревью): `payout_gross` — начислено до комиссии; `fee_amount` — creator fee по terms_version (для Content Rewards: CPM всегда 10%; per-post/retainer с бюджетом ≥ threshold → 0%; creator fee ≠ brand/platform fee — не смешивать); `payout_net = payout_gross − fee_amount` — то, что попадает в wallet. Ожидание (expected) и факт (actual) — раздельные поля; снапшоты хранят кумулятив gross и net.

## CR-0.3 Машина состояний RewardSubmission + матрица переходов
Статусы: `draft → ready → posted → submission_required → submitted → pending → approved|rejected|flagged → validating → paid|reversed`; служебные: `expired`, `failed`.
Явная матрица (прочее — 409 `invalid_status_transition`):

| from | to | триггер | evidence |
|---|---|---|---|
| draft | ready | user (подтверждение после compliance passed) | compliance_run_id |
| ready | posted | system (публикация подтверждена пользователем) | publication_id, posted_render_sha256 |
| posted | submission_required | system (автоматически, старт countdown) | — |
| posted | expired | system (дедлайн прошёл без submitted) | deadline_at |
| submission_required | submitted | user (manual-подтверждение) или provider (api) | submit confirmation |
| submitted | pending | user/provider | — |
| pending | approved / rejected / flagged | provider → user вводит факт | rejection_reason при rejected |
| flagged | pending / rejected | user | note |
| approved | validating | system (CPM: окно earnings) | terms_version |
| approved | paid | system/user (per-post/retainer без окна) | paid_at |
| validating | paid / reversed | system/user | payout snapshots |
| paid | reversed | user (диспут) | evidence обязателен |
| draft/ready/submission_required | failed | system (техошибка) | last_error |
| failed | ready | user (retry) | — |

`POST /api/v1/reward-submissions/{id}/decision` — ЕДИНЫЙ эндпоинт решений (approve/reject/flag/paid/reversed/ready-retry) c телом `{decision, evidence, idempotency_key}`: строго по матрице; каждый переход = строка в `reward_submission_events` (from/to/decision/actor/evidence/idempotency_key uq/created_at); повтор с тем же idempotency_key → 200 с существующим результатом без дублирования события; незаконный переход → 409.

## CR-3.2 Правила compliance (rule_code → severity)
`platform_allowed` blocker · `duration_in_range` blocker · `required_hashtags` blocker · `required_mentions` blocker · `disclosure_present` blocker · `source_authorized` blocker · `source_hash_match` blocker · `logo_requirement` manual_review (визуальное — без подтверждения не считается выполненным) · `music_requirement` manual_review · `safe_zones` manual_review · `duplicate_similarity` blocker/warning (порог настраиваемый) · `render_hash_immutable` blocker · `campaign_active` blocker · `budget_freshness` warning · `brief_stale` warning · `deadline_window` blocker. Ошибка правила → run.status=error, публикация запрещена до перезапуска.

## CR-4. RewardProvider + факты (KNOWLEDGE §7–§8, проверено 2026-09-22)
`Protocol`: `provider_id`; `capabilities() -> {campaigns, submission, status, payouts}`; `list_campaigns/import_campaign/submit/refresh_status/refresh_payout`. Первый — `ManualContentRewardsProvider` (все capabilities false; готовит deep-link формы, checklist, countdown; факты вносит пользователь). **Формулировка по API (по ревью)**: официальный creator API для Content Rewards **не найден на дату проверки 2026-09-22**; ревизия индекса docs.whop.com/llms.txt выполнена **частично** (выборочные чанки из 32) — **полная ревизия обязательна перед любой автоматизацией CR-4**; Bounties API ≠ Content Rewards. Instagram — официальный adapter в реестре Publisher: container flow (`media` media_type=REELS + публичный video_url → poll status_code → `media_publish`); **scopes**: Instagram Login — `instagram_business_basic`+`instagram_business_content_publish`; Facebook Login — `instagram_basic`+`instagram_content_publish`+`pages_read_engagement` (+ads_* при Business Manager); нужен Advanced Access (App Review) и учёт PPA; лимит 100 API-постов/24ч (enforced на media_publish). Без прав — ручной fallback. Никакого scraping/bots.

## CR-6. Forecast (контракт формул)
- **CPM**: `E[net] = min(max(views_D7_verified_pred/1000 × cpm_rate, min_payout), max_payout_per_clip) × P(approval) × P(fraud_clear) × budget_factor × (1 − fee%)`; `budget_factor = clamp(budget_left/budget_total, 0..1)` по последнему снимку (warning при устаревании).
- **per_post**: `E[net] = per_post_amount × P(approval) × (1 − fee%)`; **retainer**: `E[net] = retainer_amount × (deliverables_done/total|1) × P(approval) × (1 − fee%)`.
- `Payout/hour = E[net] / active_hours(production_sessions)`. Expected/actual раздельно (CR-0.4). Portfolio 50/25/15/10 — конфигурируемые веса, не константа.

## CR-7. Payout-aware ML (контракт)
Dataset: clip features + campaign features (payout_model, cpm, budget_factor, platform) + account context + D0/D1/D3/D7 verified views + approval/rejection+reason + actual gross/fee/net + production minutes. Targets: primary `net_verified_payout`; ranking `net_verified_payout_per_active_hour`. Engines: `approval_classifier`, `view_forecast_{3h,1d,7d}`, `payout_regression`, `learning_to_rank` (позже contextual bandit). Split time/campaign/account-aware; leakage-тесты обязательны. Shadow mode → активация только при превосходстве champion; `insufficient_data` — честный ответ; drift/feature mismatch/битый artifact → эвристика; rollback на предыдущую модель. Первые 50–100 публикаций — контролируемый сбор данных. Внешняя популярность (CR-8) — prior для признаков, НЕ payout label. Артефакты: hash, model type, feature schema hash, training window, dataset size, val metrics, created_at, role champion|shadow|retired.

## CR-4.3 Публичные API (семейства)
`/api/v1/reward-campaigns` (CRUD+import text/file/JSON) · `/{id}/brief` (GET версии; POST парс → pending_approval; PATCH approve/reject) · `/{id}/rank` · `/{id}/source-assets` (+авторизация) · `/{id}/terms` (GET история; POST новая версия; PATCH подтверждение) · `/api/v1/clips/{id}/compliance` (POST прогон; GET последний) · `/api/v1/reward-submissions` · `/{id}/submit` (manual-подтверждение/api; idempotent) · `/{id}/snapshots` · `/{id}/decision` (CR-0.3) · `/api/v1/reward-analytics/summary` (6 KPI + urgent deadlines + budget risk) · `/api/v1/reward-models/train` + `/runs` (shadow/activate/rollback) · OAuth/connect Instagram. Правила: ошибки §1; idempotency; публикация и submission — только после явного подтверждения (409 `user_confirmation_required`).
